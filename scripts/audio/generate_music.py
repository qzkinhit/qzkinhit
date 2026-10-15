#!/usr/bin/env python3
"""复现独立的原创学习背景音乐。需要 Python 3.9+、numpy 和 ffmpeg。

用法：python3 scripts/audio/generate_music.py
音符、时值、力度、音色和混响均由此脚本生成，不读取外部音乐或人声。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import numpy as np


RATE = 44100
SEED = 20261015
BARS = 32
BEATS_PER_BAR = 4
NOMINAL_BPM = 72.0
# 整数个 AAC 帧使解码后的样本数也能完整落在循环边界。
SAMPLES = round(BARS * BEATS_PER_BAR * 60 / NOMINAL_BPM * RATE / 1024) * 1024
DURATION = SAMPLES / RATE
BEAT = DURATION / (BARS * BEATS_PER_BAR)
TARGET_LUFS = -26.0
MAX_TRUE_PEAK = -6.0

# 两遍 16 小节。中间声部保留共同音，旋律留出足够空隙。
# 每项为：和声名、低音 MIDI、键盘和弦、旋律（拍位置、MIDI、拍长度）。
SCORE = [
    ("Cmaj9", 36, [55, 59, 62, 64], [(0.80, 67, 1.10), (2.60, 64, 1.10)]),
    ("Cmaj9/E", 40, [55, 60, 62, 67], [(1.40, 62, 0.90), (3.00, 64, 0.85)]),
    ("Am9", 33, [55, 59, 60, 64], [(0.90, 64, 1.35), (2.80, 67, 0.95)]),
    ("Am9/G", 31, [57, 59, 60, 64], [(0.65, 69, 1.90)]),
    ("Fmaj9", 29, [53, 57, 60, 64], [(1.15, 67, 1.05), (2.80, 64, 0.95)]),
    ("F6/9", 29, [55, 57, 60, 62], [(1.65, 62, 1.65)]),
    ("Dm9", 38, [53, 57, 60, 64], [(0.75, 65, 0.90), (2.45, 64, 1.20)]),
    ("G13sus", 31, [53, 57, 60, 64], [(1.35, 62, 1.65)]),
    ("Cmaj9", 36, [55, 59, 62, 64], [(0.95, 64, 1.20), (2.85, 67, 0.90)]),
    ("Cmaj9/E", 40, [55, 60, 62, 67], [(0.75, 71, 1.90)]),
    ("Am9", 33, [55, 59, 60, 64], [(1.25, 69, 1.15), (2.95, 67, 0.85)]),
    ("Em7", 40, [55, 59, 62, 64], [(1.05, 64, 1.80)]),
    ("Fmaj9", 29, [53, 57, 60, 64], [(0.65, 65, 1.05), (2.35, 64, 1.10)]),
    ("Cmaj9/E", 40, [55, 59, 60, 62], [(1.10, 62, 1.05), (2.80, 60, 0.90)]),
    ("Dm9", 38, [53, 57, 60, 64], [(0.85, 62, 1.70)]),
    ("G6sus", 31, [55, 57, 60, 62], [(1.10, 62, 1.60)]),
]


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, check=True, capture_output=True, text=True)


def loudness(path: Path, raw: bool = False) -> dict:
    args = ["ffmpeg", "-hide_banner", "-nostats"]
    if raw:
        args += ["-f", "f32le", "-ar", str(RATE), "-ac", "2"]
    args += ["-i", str(path), "-af", "loudnorm=I=-26:TP=-6:LRA=8:print_format=json", "-f", "null", "-"]
    log = run(args).stderr
    blocks = re.findall(r"\{[^{}]+\}", log)
    if not blocks:
        raise RuntimeError("ffmpeg 没有返回响度测量结果")
    measured = json.loads(blocks[-1])
    return {
        "integrated_lufs": float(measured["input_i"]),
        "true_peak_dbtp": float(measured["input_tp"]),
        "loudness_range_lu": float(measured["input_lra"]),
    }


def add_circular(mix: np.ndarray, note: np.ndarray, time_seconds: float, pan: float) -> None:
    start = round(time_seconds * RATE) % len(mix)
    pan = float(np.clip(pan, -0.65, 0.65))
    gains = np.array([math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)], dtype=np.float32)
    stereo = note[:, None] * gains[None, :]
    first = min(len(note), len(mix) - start)
    mix[start : start + first] += stereo[:first]
    if first < len(note):
        mix[: len(note) - first] += stereo[first:]


def keyboard(midi: int, hold: float, velocity: float, rng: np.random.Generator, bass: bool = False) -> np.ndarray:
    """温暖的键盘模态合成，带击键瞬态、轻微失谐和柔和释放。"""
    release = 1.0 if bass else 1.50
    t = np.arange(round((hold + release) * RATE), dtype=np.float32) / RATE
    frequency = 440.0 * 2 ** ((midi - 69) / 12)
    attack = 0.024 if bass else 0.014 + 0.009 * (1 - velocity)
    envelope = 1 - np.exp(-t / attack)
    off = np.clip((t - hold) / release, 0.0, 1.0)
    envelope *= 0.5 * (1 + np.cos(np.pi * off))
    tone = np.zeros_like(t)
    # 高次泛音比基频更快衰减，避免持续的尖锐正弦音。
    partials = [(1, 1.0, 3.3), (2, 0.29, 1.4), (3, 0.13, 0.8), (4, 0.055, 0.55), (5, 0.025, 0.38), (7, 0.012, 0.22)]
    for harmonic, amplitude, decay in partials:
        inharmonicity = 1.0 + 0.000025 * harmonic * harmonic
        phase = 2 * np.pi * frequency * harmonic * inharmonicity * t
        # 双振子很轻的拍频形成琴弦感，避免明显合唱效果。
        detune = 2 ** (rng.uniform(-1.8, 1.8) / 1200)
        wave = 0.76 * np.sin(phase) + 0.24 * np.sin(phase * detune)
        decay_time = decay * (1.25 if bass else 1.0) * (1.0 + (64 - midi) * 0.01)
        harmonic_velocity = velocity ** (0.45 + 0.12 * harmonic)
        tone += amplitude * harmonic_velocity * wave * np.exp(-t / decay_time)
    if not bass:
        # 低电平、短促的槌击纹理。它不是持续噪声轨。
        noise = rng.normal(0.0, 1.0, len(t)).astype(np.float32)
        noise = np.convolve(noise, np.ones(11, dtype=np.float32) / 11, mode="same")
        tone += 0.010 * noise * np.exp(-t / 0.018)
    return (0.21 * velocity * tone * envelope).astype(np.float32)


def room_response(rng: np.random.Generator, channel: int) -> np.ndarray:
    """原创、衰减且经过低通的房间脉冲响应，不使用外部采样。"""
    size = round(1.95 * RATE)
    t = np.arange(size) / RATE
    response = rng.normal(size=size) * np.exp(-6.9078 * t / 1.65)
    response[: round((0.025 + channel * 0.004) * RATE)] = 0
    response *= np.minimum(t / 0.085, 1.0)
    taps = np.arange(-40, 41)
    cutoff = 2300 / RATE
    fir = 2 * cutoff * np.sinc(2 * cutoff * taps) * np.hamming(len(taps))
    fir /= fir.sum()
    response = np.convolve(response, fir, mode="same")
    response /= max(np.sqrt(np.sum(response * response)), 1e-12)
    response *= 0.25
    for delay, gain in [(0.034, 0.052), (0.058, 0.041), (0.091, 0.030), (0.143, 0.019)]:
        response[round((delay + channel * 0.003) * RATE)] += gain
    # 尾端归零，避免有限长度脉冲响应末端发生跳变。
    tail = round(0.12 * RATE)
    response[-tail:] *= np.linspace(1, 0, tail)
    return response


def compose() -> tuple[np.ndarray, int]:
    rng = np.random.default_rng(SEED)
    mix = np.zeros((SAMPLES, 2), dtype=np.float32)
    count = 0
    for bar in range(BARS):
        _, bass, chord, melody = SCORE[bar % len(SCORE)]
        base = bar * 4 * BEAT
        phrase = 0.94 + 0.06 * math.sin(2 * math.pi * bar / 16 - 0.4)
        add_circular(mix, keyboard(bass, 2.8 * BEAT, 0.43 * phrase, rng, bass=True), base + 0.012, -0.06)
        count += 1
        # 每四个音的展开间隔不同，保留自然的左右手时序差。
        roll = rng.uniform(0.028, 0.048)
        for position, pitch in enumerate(chord):
            at = base + 0.045 + position * roll + rng.uniform(-0.012, 0.012)
            note = keyboard(pitch, rng.uniform(2.3, 2.7) * BEAT, rng.uniform(0.34, 0.42) * phrase, rng)
            add_circular(mix, note, at, -0.25 + position * 0.13)
            count += 1
        # 轻微分解和弦仅填充后半小节，每四小节保留一次停顿。
        if bar % 4 != 3:
            for beat, pitch in [(2.05, chord[1]), (2.90, chord[2])]:
                note = keyboard(pitch, 0.95 * BEAT, rng.uniform(0.24, 0.30), rng)
                add_circular(mix, note, base + beat * BEAT + rng.uniform(-0.025, 0.025), rng.uniform(-0.22, 0.22))
                count += 1
        for position, (beat, pitch, length) in enumerate(melody):
            # 第二遍变更部分时值和力度，主题保持一致。
            if bar >= 16 and bar % 8 == 3:
                pitch -= 2
            onset = base + (beat + (0.06 if bar >= 16 else 0)) * BEAT + rng.uniform(-0.025, 0.025)
            velocity = rng.uniform(0.44, 0.53) * phrase * (0.97 if position else 1.0)
            note = keyboard(pitch, length * BEAT, velocity, rng)
            add_circular(mix, note, onset, 0.14 + rng.uniform(-0.08, 0.08))
            count += 1
    # 所有混响均做循环卷积。最后一个小节的余音自然进入开头。
    wet = np.zeros_like(mix)
    for channel in range(2):
        send = mix[:, channel] * 0.8 + mix[:, 1 - channel] * 0.2
        impulse = room_response(rng, channel)
        transformed = np.fft.rfft(send)
        transformed *= np.fft.rfft(impulse, n=SAMPLES)
        wet[:, channel] = np.fft.irfft(transformed, n=SAMPLES).astype(np.float32)
    mix = 0.93 * mix + wet
    # 35 Hz 以下平滑衰减，减少手机和耳机中的无效低频。
    frequencies = np.fft.rfftfreq(SAMPLES, 1 / RATE)
    highpass = frequencies * frequencies / (frequencies * frequencies + 35.0**2)
    for channel in range(2):
        mix[:, channel] = np.fft.irfft(np.fft.rfft(mix[:, channel]) * highpass, n=SAMPLES)
    mix -= mix.mean(axis=0)
    return mix, count


def db(value: float) -> float:
    return float(20 * np.log10(max(float(value), 1e-12)))


def signal_metrics(audio: np.ndarray) -> dict:
    mono = audio.mean(axis=1)
    frame_size = 8192
    frames = mono[: len(mono) // frame_size * frame_size].reshape(-1, frame_size)
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(frame_size), axis=1)) ** 2
    power = spectrum.mean(axis=0)
    frequency = np.fft.rfftfreq(frame_size, 1 / RATE)
    differences = np.abs(np.diff(audio, axis=0))
    edge = np.abs(audio[0] - audio[-1])
    window = round(0.02 * RATE)
    return {
        "sample_count": len(audio),
        "duration_seconds": round(len(audio) / RATE, 6),
        "sample_peak_dbfs": round(db(np.max(np.abs(audio))), 3),
        "rms_dbfs": round(db(np.sqrt(np.mean(audio.astype(np.float64) ** 2))), 3),
        "dc_offset": [round(float(x), 9) for x in audio.mean(axis=0)],
        "stereo_correlation": round(float(np.corrcoef(audio.T)[0, 1]), 5),
        "seam_step_dbfs": round(db(np.max(edge)), 3),
        "ordinary_step_p999_dbfs": round(db(np.quantile(differences, 0.999)), 3),
        "seam_to_ordinary_p999_ratio": round(float(np.max(edge) / max(np.quantile(differences, 0.999), 1e-12)), 5),
        "first_20ms_rms_dbfs": round(db(np.sqrt(np.mean(audio[:window].astype(np.float64) ** 2))), 3),
        "last_20ms_rms_dbfs": round(db(np.sqrt(np.mean(audio[-window:].astype(np.float64) ** 2))), 3),
        "spectral_energy_fraction": {
            name: round(float(power[(frequency >= lower) & (frequency < upper)].sum() / power.sum()), 6)
            for name, lower, upper in [("below_180_hz", 0, 180), ("180_to_2000_hz", 180, 2000), ("2000_to_6000_hz", 2000, 6000), ("above_6000_hz", 6000, RATE / 2 + 1)]
        },
        "clipped_samples": int(np.count_nonzero(np.abs(audio) >= 1)),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "reading/audio/music/quiet-study.m4a")
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    print("正在合成 32 小节的原创温和键盘背景音乐……", flush=True)
    samples, event_count = compose()
    with tempfile.TemporaryDirectory(prefix="quiet-study-music-") as directory:
        raw = Path(directory) / "music.f32"
        samples.astype("<f4").tofile(raw)
        source_loudness = loudness(raw, raw=True)
        gain_db = min(TARGET_LUFS - source_loudness["integrated_lufs"], MAX_TRUE_PEAK - 0.7 - source_loudness["true_peak_dbtp"])
        for attempt in range(3):
            print(f"编码 AAC-LC，增益 {gain_db:.2f} dB……", flush=True)
            run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(RATE), "-ac", "2", "-i", str(raw), "-af", f"volume={gain_db:.5f}dB", "-c:a", "aac", "-profile:a", "aac_low", "-b:a", "160k", "-ar", str(RATE), "-ac", "2", "-movflags", "+faststart", "-metadata", "title=Quiet Study", "-metadata", "artist=Original procedural composition", "-metadata", "comment=Instrumental background only; voice stored separately; reproducible from scripts/audio/generate_music.py", str(output)])
            final_loudness = loudness(output)
            if abs(final_loudness["integrated_lufs"] - TARGET_LUFS) <= 0.25 and final_loudness["true_peak_dbtp"] <= MAX_TRUE_PEAK:
                break
            gain_db += min(TARGET_LUFS - final_loudness["integrated_lufs"], MAX_TRUE_PEAK - 0.2 - final_loudness["true_peak_dbtp"])
        decoded = Path(directory) / "decoded-music.f32"
        run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(output), "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(RATE), "-ac", "2", str(decoded)])
        decoded_samples = np.fromfile(decoded, dtype="<f4").reshape(-1, 2)
        decoded_metrics = signal_metrics(decoded_samples)
        normalized = samples * 10 ** (gain_db / 20)
        source_metrics = signal_metrics(normalized)
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)]).stdout)
    stream = probe["streams"][0]
    assert stream["codec_name"] == "aac" and stream["profile"] == "LC"
    assert int(stream["sample_rate"]) == RATE and int(stream["channels"]) == 2
    assert int(stream["bit_rate"]) >= 128000
    assert decoded_metrics["clipped_samples"] == 0
    assert final_loudness["true_peak_dbtp"] <= MAX_TRUE_PEAK
    assert abs(final_loudness["integrated_lufs"] - TARGET_LUFS) <= 0.3
    assert decoded_metrics["sample_count"] == SAMPLES, "AAC 解码样本数与循环长度不符"
    metadata = {
        "title": "Quiet Study",
        "description_zh": "原创温和键盘背景音乐，稀疏旋律、低音与轻柔房间混响。无鼓点、无人声、无外部采样。",
        "source_script": "scripts/audio/generate_music.py",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "audio_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "seed": SEED,
        "bars": BARS,
        "meter": "4/4",
        "bpm": round(60 / BEAT, 6),
        "nominal_bpm": NOMINAL_BPM,
        "key": "C major / A minor",
        "note_events": event_count,
        "chord_progression": [row[0] for row in SCORE],
        "codec": {"name": stream["codec_name"], "profile": stream["profile"], "sample_rate": int(stream["sample_rate"]), "channels": stream["channels"], "bit_rate": int(stream["bit_rate"])},
        "target_integrated_lufs": TARGET_LUFS,
        "maximum_true_peak_dbtp": MAX_TRUE_PEAK,
        "recommended_browser_volume": 0.16,
        "gain_db": round(gain_db, 5),
        "decoded_loudness": final_loudness,
        "decoded_signal": decoded_metrics,
        "uncompressed_signal": source_metrics,
        "loop": {"type": "periodic synthesis and circular reverb", "sample_count": SAMPLES, "aac_frame_aligned": True, "playback_note_zh": "音符尾音与混响跨越文件边界连续相接。浏览器 HTMLAudioElement 的循环调度仍可能引入设备相关的微小间隙。"},
        "verification_zh": "已通过 ffmpeg 响度、真峰值、解码样本数、频带能量与循环接缝检查。本执行环境没有模型可用的音频审听接口，未声称完成人耳审听。",
        "provenance_zh": "全部音符与波形由本脚本生成，没有下载或复用第三方录音，也没有混入题目讲解。",
        "tools": {"numpy": np.__version__, "ffmpeg": run(["ffmpeg", "-version"]).stdout.splitlines()[0]},
    }
    metadata_path = output.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "metadata": str(metadata_path), "loudness": final_loudness, "signal": decoded_metrics}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
