#!/usr/bin/env python3
"""Generate separate, reproducible narration tracks for the swipe question bank."""

import argparse
import asyncio
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reading/audio/hot100-natural"
SOURCE = Path(__file__).parent / "narrations"


def load_sources():
    page = (ROOT / "reading/09-swipe.html").read_text()
    match = re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S)
    problems = json.loads(match.group(1))["probs"]
    narrations = {}
    for path in sorted(SOURCE.glob("part-*.json")):
        part = json.loads(path.read_text())
        overlap = narrations.keys() & part.keys()
        if overlap:
            raise ValueError(f"Duplicate narration IDs in {path}: {sorted(overlap)}")
        narrations.update(part)
    unknown = narrations.keys() - problems.keys()
    if unknown:
        raise ValueError(f"Unknown question IDs: {sorted(unknown)}")
    for key, item in narrations.items():
        if item["title"] != problems[key]["title"]:
            raise ValueError(f"Title mismatch for {key}")
        paragraphs = item["paragraphs"]
        if not 3 <= len(paragraphs) <= 9 or not all(isinstance(p, str) and p.strip() for p in paragraphs):
            raise ValueError(f"Invalid paragraphs for {key}")
    return problems, narrations


def fingerprint(text, settings):
    return hashlib.sha256(json.dumps([text, settings], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def normalized_text(text):
    return re.sub(r"[\W_]", "", html.unescape(text)).lower()


async def run(*args):
    process = await asyncio.create_subprocess_exec(*map(str, args), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError(f"{args[0]} failed: {stderr.decode(errors='replace')[-1500:]}")
    return stdout.decode(), stderr.decode()


async def measure(path):
    _, stderr = await run("ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "loudnorm=I=-18:TP=-2:LRA=9:print_format=json", "-f", "null", "-")
    return json.JSONDecoder().raw_decode(stderr[stderr.rfind("{"):])[0]


async def inspect(path):
    stdout, _ = await run("ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,sample_rate,channels,bit_rate", "-of", "json", path)
    info = json.loads(stdout)
    return {"duration": round(float(info["format"]["duration"]), 3), "bytes": int(info["format"]["size"]), **info["streams"][0]}


async def synthesize(key, item, settings, retries):
    text = "\n\n".join(item["paragraphs"])
    for attempt in range(retries):
        try:
            with tempfile.TemporaryDirectory(prefix=f"qzkinhit-tts-{key}-") as tmp:
                raw = Path(tmp) / "source.mp3"
                chunks = []
                speech = edge_tts.Communicate(text, voice=settings["voice"], rate=settings["rate"], pitch=settings["pitch"], boundary="SentenceBoundary", receive_timeout=90)
                with raw.open("wb") as stream:
                    async for chunk in speech.stream():
                        if chunk["type"] == "audio":
                            stream.write(chunk["data"])
                        elif chunk["type"] in ("SentenceBoundary", "WordBoundary"):
                            chunks.append({"text": chunk["text"], "offset": chunk["offset"], "duration": chunk["duration"]})
                spoken = normalized_text("".join(c["text"] for c in chunks))
                expected = normalized_text(text)
                if spoken != expected:
                    raise RuntimeError(f"Speech boundary text does not match script ({len(spoken)}/{len(expected)} characters)")
                levels = await measure(raw)
                filters = (
                    "loudnorm=I=-18:TP=-2:LRA=9:"
                    f"measured_I={levels['input_i']}:measured_TP={levels['input_tp']}:"
                    f"measured_LRA={levels['input_lra']}:measured_thresh={levels['input_thresh']}:"
                    f"offset={levels['target_offset']}:linear=true"
                )
                staged = OUTPUT / f".{key}.pending.mp3"
                await run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", raw, "-af", filters, "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "64k", "-metadata", f"title={item['title']}", "-metadata", "artist=中文合成女声 · 晓晓", "-metadata", "album=Hot 100 自然讲解", staged)
                info = await inspect(staged)
                if not len(text) * 0.11 < info["duration"] < len(text) * 0.8:
                    raise RuntimeError(f"Unexpected audio duration for {key}: {info['duration']}")
                final_levels = await measure(staged)
                if not -19.2 <= float(final_levels["input_i"]) <= -16.8 or float(final_levels["input_tp"]) > -0.7:
                    raise RuntimeError(f"Audio levels outside target for {key}: {final_levels}")
                destination = OUTPUT / f"{key}.mp3"
                staged.replace(destination)
                return {
                    "title": item["title"], "file": f"{key}.mp3", "scriptSha256": fingerprint(text, settings),
                    "audioSha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
                    "characters": len(text), "spokenTextVerified": True, "sentences": len(chunks), "settings": settings,
                    "integratedLufs": float(final_levels["input_i"]), "truePeakDbtp": float(final_levels["input_tp"]),
                    **info,
                }
        except Exception as error:
            if attempt == retries - 1:
                raise
            print(f"RETRY {key} {attempt + 1}/{retries}: {error}", flush=True)
            await asyncio.sleep(min(3 * (attempt + 1), 12))


async def main(args):
    for command in ("ffmpeg", "ffprobe"):
        if not shutil.which(command):
            raise RuntimeError(f"{command} is required")
    problems, narrations = load_sources()
    ids = args.ids.split(",") if args.ids else list(problems)
    missing = set(ids) - narrations.keys()
    if missing:
        raise ValueError(f"Missing narration scripts: {sorted(missing)}")
    if args.check_only:
        print(f"Verified {len(ids)} narration scripts; question bank contains {len(problems)} questions")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"schemaVersion": 1, "tracks": {}}
    settings = {"engine": "Microsoft Edge neural TTS", "libraryVersion": edge_tts.__version__, "voice": args.voice, "rate": args.rate, "pitch": args.pitch, "integratedLufs": -18, "truePeakLimitDbtp": -2, "sampleRate": 24000, "bitRate": 64000}
    semaphore = asyncio.Semaphore(args.jobs)
    failures = []
    completed = 0

    def save_manifest():
        manifest.update({"generatedAt": datetime.now(timezone.utc).isoformat(), "settings": settings, "musicIncluded": False, "totalQuestions": len(problems)})
        manifest["tracks"] = {key: manifest["tracks"][key] for key in problems if key in manifest["tracks"]}
        staging = manifest_path.with_suffix(".tmp")
        staging.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        staging.replace(manifest_path)

    async def work(key):
        nonlocal completed
        async with semaphore:
            try:
                text = "\n\n".join(narrations[key]["paragraphs"])
                current = manifest["tracks"].get(key, {})
                path = OUTPUT / f"{key}.mp3"
                if not args.force and current.get("scriptSha256") == fingerprint(text, settings) and path.exists() and current.get("audioSha256") == hashlib.sha256(path.read_bytes()).hexdigest():
                    status = "CACHED"
                else:
                    manifest["tracks"][key] = await synthesize(key, narrations[key], settings, args.retries)
                    save_manifest()
                    status = "READY"
                completed += 1
                info = manifest["tracks"][key]
                print(f"{status} {completed}/{len(ids)} {key} {info['title']} {info['duration']}s {info['integratedLufs']} LUFS", flush=True)
            except Exception as error:
                failures.append(key)
                print(f"FAILED {key}: {error}", flush=True)

    await asyncio.gather(*(work(key) for key in ids))
    save_manifest()
    if failures:
        raise RuntimeError(f"Generation failed for: {','.join(failures)}. Rerun to retry only incomplete tracks.")
    if not args.ids and set(manifest["tracks"]) != set(problems):
        raise RuntimeError("Manifest coverage differs from question bank")
    print(f"Finished {len(ids)} tracks. Narration and music remain separate files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", help="Comma-separated IDs; default is the complete question bank")
    parser.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    parser.add_argument("--rate", default="-3%")
    parser.add_argument("--pitch", default="-1Hz")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    arguments = parser.parse_args()
    if not 1 <= arguments.jobs <= 6 or not 1 <= arguments.retries <= 8:
        parser.error("Use 1–6 jobs and 1–8 retries")
    asyncio.run(main(arguments))
