#!/usr/bin/env python3
"""Validate complete question coverage, reproducibility metadata and actual media."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
VOICE_DIR = ROOT / "reading/audio/hot100-natural"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def decode(path):
    result = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    require(result.returncode == 0 and not result.stderr.strip(), f"Decode error in {path.name}: {result.stderr[-500:]}")


def main(args):
    page = (ROOT / "reading/09-swipe.html").read_text()
    data = json.loads(re.search(r'<script type="application/json" id="data">(.*?)</script>', page, re.S).group(1))
    ids = set(data["probs"])
    narrations = {}
    for path in sorted((ROOT / "scripts/audio/narrations").glob("part-*.json")):
        part = json.loads(path.read_text())
        require(not narrations.keys() & part.keys(), f"Duplicate narration IDs in {path}")
        narrations.update(part)
    manifest = json.loads((VOICE_DIR / "manifest.json").read_text())
    tracks = manifest["tracks"]
    require(set(narrations) == ids, "Narration coverage differs from question bank")
    require(set(tracks) == ids, "Manifest coverage differs from question bank")
    files = {path.stem for path in VOICE_DIR.glob("*.mp3") if not path.name.startswith(".")}
    require(files == ids, "Audio file coverage differs from question bank")
    require(manifest["totalQuestions"] == len(ids) and manifest["musicIncluded"] is False, "Invalid voice manifest")

    def check_voice(key):
        item = tracks[key]
        require(item["file"] == key + ".mp3", f"Invalid path for {key}")
        path = VOICE_DIR / item["file"]
        require(item["title"] == narrations[key]["title"] == data["probs"][key]["title"], f"Title mismatch for {key}")
        text = "\n\n".join(narrations[key]["paragraphs"])
        settings = item.get("settings", manifest["settings"])
        expected = hashlib.sha256(json.dumps([text, settings], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        require(item["scriptSha256"] == expected, f"Stale narration audio for {key}")
        require(item["audioSha256"] == digest(path), f"Audio checksum mismatch for {key}")
        require(item["spokenTextVerified"] is True and item["characters"] == len(text), f"Spoken text coverage not verified for {key}")
        info = probe(path)
        require(len(info["streams"]) == 1, f"Expected one pure narration stream for {key}")
        stream = info["streams"][0]
        require(stream["codec_name"] == "mp3" and stream["channels"] == 1 and stream["sample_rate"] == "24000", f"Wrong narration format for {key}")
        duration = float(info["format"]["duration"])
        require(abs(duration - item["duration"]) < 0.01 and path.stat().st_size == item["bytes"], f"Duration/size mismatch for {key}")
        require(len(text) * 0.11 < duration < len(text) * 0.8, f"Implausible duration for {key}")
        require(-19.2 <= item["integratedLufs"] <= -16.8 and item["truePeakDbtp"] <= -0.7, f"Audio levels outside target for {key}")
        if not args.metadata_only:
            decode(path)
        return duration

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        durations = list(executor.map(check_voice, sorted(ids)))

    music_path = ROOT / "reading/audio/music/quiet-study.m4a"
    music_meta = json.loads(music_path.with_suffix(".metadata.json").read_text())
    require(music_meta["audio_sha256"] == digest(music_path), "Background music checksum mismatch")
    require(music_meta["source_sha256"] == digest(ROOT / music_meta["source_script"]), "Background music generation script changed")
    music = probe(music_path)
    require(len(music["streams"]) == 1, "Expected one standalone music stream")
    stream = music["streams"][0]
    require(stream["codec_name"] == "aac" and stream["profile"] == "LC" and stream["channels"] == 2 and stream["sample_rate"] == "44100", "Wrong music format")
    require(music_meta["decoded_signal"]["clipped_samples"] == 0 and music_meta["decoded_loudness"]["true_peak_dbtp"] <= -6, "Background music peak outside target")
    if not args.metadata_only:
        decode(music_path)

    report = {
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
        "questionCount": len(ids), "narrationCount": len(tracks), "musicCount": 1,
        "allFilesDecoded": not args.metadata_only, "allScriptAndAudioChecksumsMatch": True,
        "totalNarrationMinutes": round(sum(durations) / 60, 2),
        "listeningMinutesAtDefaultRate": round(sum(durations) / 60 / 1.2, 2),
        "shortestNarrationSeconds": min(durations), "longestNarrationSeconds": max(durations),
        "totalNarrationBytes": sum(item["bytes"] for item in tracks.values()),
        "narrationLufsRange": [min(item["integratedLufs"] for item in tracks.values()), max(item["integratedLufs"] for item in tracks.values())],
        "highestNarrationTruePeakDbtp": max(item["truePeakDbtp"] for item in tracks.values()),
        "musicSeconds": float(music["format"]["duration"]),
        "musicLufs": music_meta["decoded_loudness"]["integrated_lufs"],
        "musicTruePeakDbtp": music_meta["decoded_loudness"]["true_peak_dbtp"],
        "separateNarrationAndMusicFiles": True,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata-only", action="store_true", help="Skip full decoding, still check every file and checksum")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--report", help="Optional path for a JSON verification report")
    arguments = parser.parse_args()
    if not 1 <= arguments.jobs <= 8:
        parser.error("jobs must be between 1 and 8")
    main(arguments)
