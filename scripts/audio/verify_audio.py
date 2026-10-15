#!/usr/bin/env python3
"""校验独立讲解音轨、固定来源快照，以及实际解码后的思考静音。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COLLECTIONS = {
    "hot100": {"page": "reading/09-swipe.html", "narrations": "scripts/audio/narrations"},
    "papers": {"page": "reading/10-papers.html", "narrations": "scripts/audio/narrations-papers"},
    "bagu": {"page": "reading/11-bagu.html", "narrations": "scripts/audio/narrations-bagu"},
}
CONTENT_FIELDS = ("q", "a", "key", "f", "plain", "fq", "fa", "nums", "cmp")
SILENCE_DBFS = -60
SILENCE_MIN_SECONDS = 0.05
PAUSE_EDGE_SECONDS = 0.1
MIN_PAUSE_SECONDS = 0.3


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def canonical_digest(value):
    # 与生成器一致，包含 json.dumps 默认分隔符中的空格。
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"Invalid finite number for {label}")
    return float(value)


def page_data(path):
    page = Path(path).read_text(encoding="utf-8")
    match = re.search(r'<script\b[^>]*\bid\s*=\s*([\'"])data\1[^>]*>(.*?)</script\s*>', page, re.S | re.I)
    require(match is not None, f"Missing id=data JSON in {path}")
    return json.loads(match.group(2), object_pairs_hook=unique_object)


def current_cards(collection, data):
    if collection == "papers":
        require(isinstance(data, list), "Expected a list of paper collections")
        pairs = [(f"{paper['id']}-{index + 1}", card) for paper in data for index, card in enumerate(paper["cards"])]
    elif collection == "bagu":
        require(isinstance(data, dict) and isinstance(data.get("cards"), list), "Expected bagu cards list")
        pairs = [(card["id"], card) for card in data["cards"]]
    else:
        return data["probs"]
    return unique_object(pairs)


def current_page_changes(collection, snapshot_cards):
    path = ROOT / COLLECTIONS[collection]["page"]
    try:
        live = current_cards(collection, page_data(path))
        old_ids, new_ids = set(snapshot_cards), set(live)
        changed = []
        for key in snapshot_cards:
            if key not in live:
                continue
            previous = snapshot_cards[key]["source"]
            fields = [field for field in CONTENT_FIELDS if (field in previous) != (field in live[key]) or previous.get(field) != live[key].get(field)]
            if fields:
                changed.append({"id": key, "snapshotTitle": previous.get("q"), "currentTitle": live[key].get("q"), "changedFields": fields})
        added = [{"id": key, "title": live[key].get("q")} for key in live if key not in old_ids]
        removed = [{"id": key, "title": snapshot_cards[key]["title"]} for key in snapshot_cards if key not in new_ids]
        return {"page": str(path.relative_to(ROOT)), "status": "changed" if added or removed or changed else "unchanged", "currentCardCount": len(live), "comparedFields": list(CONTENT_FIELDS), "addedCards": added, "removedCards": removed, "changedCards": changed, "affectsValidationScope": False}
    except (OSError, ValueError, KeyError, TypeError) as error:
        # 当前页面仅作变化提示，不替代本批固定来源。
        return {"page": str(path.relative_to(ROOT)), "status": "unavailable", "error": str(error), "affectsValidationScope": False}


def load_sources(collection, snapshot_override=None):
    config = COLLECTIONS[collection]
    if collection == "hot100":
        require(snapshot_override is None, "--snapshot is only supported for papers and bagu")
        problems = current_cards(collection, page_data(ROOT / config["page"]))
        snapshot_path, snapshot = None, None
    else:
        snapshot_path = Path(snapshot_override).expanduser().resolve() if snapshot_override else ROOT / f"scripts/audio/snapshots/{collection}-20261015.json"
        snapshot = read_json(snapshot_path)
        problems = snapshot["cards"]
        require(isinstance(problems, dict) and snapshot.get("collection") == collection and snapshot.get("count") == len(problems), "Invalid fixed source snapshot")
        for key, value in problems.items():
            require(isinstance(value, dict), f"Invalid snapshot card object for {key}")
            require(value.get("id") == key and isinstance(value.get("source"), dict), f"Invalid snapshot card {key}")
            require(value.get("title") == value["source"].get("q"), f"Snapshot title mismatch for {key}")
    require(isinstance(problems, dict) and problems, "Empty or invalid question bank")
    require(all(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", key) for key in problems), "Unsafe question ID")
    narrations = {}
    for path in sorted((ROOT / config["narrations"]).glob("part-*.json")):
        part = read_json(path)
        require(isinstance(part, dict), f"Expected a narration object in {path}")
        require(not narrations.keys() & part.keys(), f"Duplicate narration IDs in {path}")
        narrations.update(part)
    return problems, narrations, snapshot_path, snapshot


def selected_ids(raw_ids, problems):
    if raw_ids is None:
        return list(problems)
    keys = [key.strip() for key in raw_ids.split(",")]
    require(keys and all(keys), "--ids must be a nonempty comma-separated list")
    require(len(keys) == len(set(keys)), "Duplicate IDs in --ids")
    require(not set(keys) - problems.keys(), f"IDs outside the fixed collection: {sorted(set(keys) - problems.keys())}")
    return keys


def coverage(expected, selected, actual_sets, partial):
    result = {}
    for label, actual in actual_sets.items():
        result[label] = {"count": len(actual), "missingIds": sorted(expected - actual), "unexpectedIds": sorted(actual - expected)}
        if partial:
            require(selected <= actual, f"Missing selected {label}: {sorted(selected - actual)}")
        else:
            require(actual == expected, f"{label} coverage differs from the collection: missing {sorted(expected - actual)}, unexpected {sorted(actual - expected)}")
    return result


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def silence_intervals(stderr, duration):
    intervals, start = [], None
    for match in re.finditer(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", stderr):
        kind, value = match.group(1), float(match.group(2))
        if kind == "start":
            require(start is None, "Unexpected nested silence_start in ffmpeg output")
            start = value
        else:
            require(start is not None and value >= start, "Unpaired silence_end in ffmpeg output")
            intervals.append((start, value))
            start = None
    if start is not None:
        require(duration >= start, "Silence starts beyond audio duration")
        intervals.append((start, duration))
    return intervals


def decode_and_measure(path, duration, detect_silence=False):
    filters = []
    if detect_silence:
        filters.append(f"silencedetect=noise={SILENCE_DBFS}dB:duration={SILENCE_MIN_SECONDS}")
    # EBU R128 只测量，不做响度归一化；帧日志降为 verbose，保留最终摘要。
    filters.append("ebur128=peak=true:framelog=verbose")
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "info", "-xerror", "-i", str(path), "-map", "0:a:0", "-af", ",".join(filters), "-f", "null", "-"], capture_output=True, text=True)
    require(result.returncode == 0, f"Decode error in {path.name}: {result.stderr[-1200:]}")
    offset = result.stderr.rfind("Summary:")
    require(offset >= 0, f"Missing measured loudness for {path.name}")
    summary = result.stderr[offset:]
    loudness = re.search(r"\bI:\s*(-?\d+(?:\.\d+)?)\s+LUFS", summary)
    peak = re.search(r"True peak:\s*Peak:\s*(-?\d+(?:\.\d+)?)\s+dBFS", summary, re.S)
    require(loudness is not None and peak is not None, f"Missing finite EBU R128 levels for {path.name}")
    return {"integratedLufs": float(loudness.group(1)), "truePeakDbtp": float(peak.group(1)), "silences": silence_intervals(result.stderr, duration) if detect_silence else []}


def check_pause_metadata(key, item, settings, duration):
    planned = number(settings.get("introPauseSeconds"), f"{key} introPauseSeconds")
    require(planned == 0 or planned >= MIN_PAUSE_SECONDS, f"Thinking pause must be zero or at least {MIN_PAUSE_SECONDS} seconds for {key}")
    pause = item.get("thinkingPause")
    if planned == 0:
        require(pause is None, f"Thinking pause is disabled but metadata declares a pause for {key}")
        return None
    require(isinstance(pause, dict), f"Missing thinkingPause for {key}")
    start = number(pause.get("startSeconds"), f"{key} pause start")
    length = number(pause.get("durationSeconds"), f"{key} pause duration")
    require(start > 0 and length >= MIN_PAUSE_SECONDS and start + length < duration, f"Invalid thinking pause interval for {key}")
    require(abs(length - planned) <= 0.000001, f"Thinking pause differs from track settings for {key}")
    return start, length


def covering_silence(key, pause, intervals):
    start, length = pause
    left, right = start + PAUSE_EDGE_SECONDS, start + length - PAUSE_EDGE_SECONDS
    for quiet_start, quiet_end in intervals:
        if quiet_start <= left + 0.000001 and quiet_end >= right - 0.000001:
            return quiet_start, quiet_end
    nearby = [(round(a, 6), round(b, 6)) for a, b in intervals if b >= start - 1 and a <= start + length + 1]
    raise ValueError(f"Thinking silence missing for {key}: must cover [{left:.6f}, {right:.6f}], detected nearby {nearby}")


def check_voice(key, collection, problems, narrations, manifest, voice_dir, metadata_only):
    item = manifest["tracks"][key]
    narration = narrations[key]
    require(item["file"] == key + ".mp3", f"Invalid path for {key}")
    path = voice_dir / item["file"]
    require(item["title"] == narration["title"] == problems[key]["title"], f"Title mismatch for {key}")
    paragraphs = narration.get("paragraphs")
    require(isinstance(paragraphs, list) and 2 <= len(paragraphs) <= 12 and all(isinstance(p, str) and p.strip() for p in paragraphs), f"Invalid narration paragraphs for {key}")
    text = "\n\n".join(paragraphs)
    settings = item.get("settings", manifest["settings"])
    require(isinstance(settings, dict), f"Invalid track settings for {key}")
    require(item["scriptSha256"] == canonical_digest([text, settings]), f"Stale narration audio for {key}")
    if collection != "hot100":
        require(isinstance(item.get("settings"), dict) and settings.get("collection") == collection, f"Missing collection track settings for {key}")
        require(item.get("sourceSha256") == canonical_digest(problems[key]), f"Stale source snapshot audio for {key}")
    require(item["audioSha256"] == digest(path), f"Audio checksum mismatch for {key}")
    require(item["spokenTextVerified"] is True and item["characters"] == len(text), f"Spoken text coverage not verified for {key}")
    info = probe(path)
    require(len(info["streams"]) == 1, f"Expected one pure narration stream for {key}")
    stream = info["streams"][0]
    require(stream["codec_type"] == "audio" and stream["codec_name"] == "mp3" and stream["channels"] == 1 and stream["sample_rate"] == "24000", f"Wrong narration format for {key}")
    require(int(stream["bit_rate"]) == 64000 and int(settings["sampleRate"]) == 24000 and int(settings["bitRate"]) == 64000, f"Wrong narration encoding settings for {key}")
    for field in ("codec_name", "sample_rate", "channels", "bit_rate"):
        require(str(item[field]) == str(stream[field]), f"Recorded encoding differs from file for {key}: {field}")
    duration = float(info["format"]["duration"])
    require(abs(duration - number(item["duration"], f"{key} duration")) < 0.01 and path.stat().st_size == item["bytes"], f"Duration/size mismatch for {key}")
    pause = check_pause_metadata(key, item, settings, duration) if collection != "hot100" else None
    minimum_ratio = 0.11 if collection == "hot100" else 0.09
    require(len(text) * minimum_ratio < duration < len(text) * 0.8 + (pause[1] if pause else 0), f"Implausible duration for {key}")
    lufs = number(item["integratedLufs"], f"{key} LUFS")
    peak = number(item["truePeakDbtp"], f"{key} true peak")
    require(-19.2 <= lufs <= -16.8 and peak <= -0.7, f"Audio levels outside target for {key}")
    result = {"id": key, "duration": duration, "bytes": item["bytes"], "integratedLufs": lufs, "truePeakDbtp": peak, "pause": pause}
    if not metadata_only:
        actual = decode_and_measure(path, duration, detect_silence=pause is not None)
        require(-19.2 <= actual["integratedLufs"] <= -16.8 and actual["truePeakDbtp"] <= -0.7, f"Decoded audio levels outside target for {key}")
        # EBU 摘要保留一位小数；生成器使用 loudnorm 的两位小数测量。
        require(abs(actual["integratedLufs"] - lufs) <= 0.3 and abs(actual["truePeakDbtp"] - peak) <= 0.3, f"Measured levels differ from manifest for {key}")
        result["measuredLufs"] = actual["integratedLufs"]
        result["measuredTruePeakDbtp"] = actual["truePeakDbtp"]
        if pause:
            result["confirmedSilence"] = covering_silence(key, pause, actual["silences"])
    return result


def check_music(metadata_only):
    path = ROOT / "reading/audio/music/quiet-study.m4a"
    metadata = read_json(path.with_suffix(".metadata.json"))
    require(metadata["audio_sha256"] == digest(path), "Background music checksum mismatch")
    source = (ROOT / metadata["source_script"]).resolve()
    require(source.is_relative_to(ROOT) and metadata["source_sha256"] == digest(source), "Background music generation script changed")
    info = probe(path)
    require(len(info["streams"]) == 1, "Expected one standalone music stream")
    stream = info["streams"][0]
    require(stream["codec_type"] == "audio" and stream["codec_name"] == "aac" and stream["profile"] == "LC" and stream["channels"] == 2 and stream["sample_rate"] == "44100" and int(stream["bit_rate"]) >= 128000, "Wrong music format")
    duration = float(info["format"]["duration"])
    lufs = number(metadata["decoded_loudness"]["integrated_lufs"], "music LUFS")
    peak = number(metadata["decoded_loudness"]["true_peak_dbtp"], "music true peak")
    require(metadata["decoded_signal"]["clipped_samples"] == 0 and peak <= -6, "Background music peak outside target")
    if not metadata_only:
        actual = decode_and_measure(path, duration)
        require(actual["truePeakDbtp"] <= -6, "Decoded background music peak outside target")
        require(abs(actual["integratedLufs"] - lufs) <= 0.3 and abs(actual["truePeakDbtp"] - peak) <= 0.3, "Measured music levels differ from metadata")
    return {"seconds": duration, "lufs": lufs, "truePeakDbtp": peak}


def validate(args):
    collection = args.collection
    problems, narrations, snapshot_path, snapshot = load_sources(collection, args.snapshot)
    keys = selected_ids(args.ids, problems)
    voice_dir = ROOT / f"reading/audio/{collection}-natural"
    manifest = read_json(voice_dir / "manifest.json")
    tracks = manifest["tracks"]
    require(isinstance(tracks, dict), "Invalid manifest tracks")
    require(manifest["totalQuestions"] == len(problems) and manifest["musicIncluded"] is False, "Invalid voice manifest")
    default_rate = number(manifest.get("defaultPlaybackRate", 1.2), "default playback rate")
    require(default_rate > 0, "Default playback rate must be positive")
    if snapshot_path:
        require(manifest.get("collection") == collection and manifest.get("scope") == "captured-card-snapshot", "Invalid collection or snapshot scope in manifest")
        require("defaultPlaybackRate" in manifest and isinstance(manifest.get("sourceSnapshot"), str), "Missing snapshot playback metadata")
        recorded_snapshot = Path(manifest["sourceSnapshot"])
        if not recorded_snapshot.is_absolute():
            recorded_snapshot = ROOT / recorded_snapshot
        require(recorded_snapshot.resolve() == snapshot_path.resolve(), "Manifest refers to another source snapshot")
    files = {path.stem for path in voice_dir.glob("*.mp3") if not path.name.startswith(".")}
    actual_sets = {"narrations": set(narrations), "manifestTracks": set(tracks), "audioFiles": files}
    coverage_report = coverage(set(problems), set(keys), actual_sets, partial=args.ids is not None)

    def check(key):
        return check_voice(key, collection, problems, narrations, manifest, voice_dir, args.metadata_only)

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        results = list(executor.map(check, keys))
    music = check_music(args.metadata_only)
    durations = [item["duration"] for item in results]
    complete_coverage = all(actual == set(problems) for actual in actual_sets.values())
    complete_selection = set(keys) == set(problems)
    pause_results = [item for item in results if item["pause"] is not None]
    pause_count = len(pause_results)
    pause_required = pause_count > 0
    measured = not args.metadata_only
    report = {
        "verifiedAt": datetime.now(timezone.utc).isoformat(), "collection": collection, "ok": True,
        "validationScope": "selected-ids" if args.ids is not None else "complete-collection",
        "sourceScope": "captured-card-snapshot" if snapshot else "current-hot100-page",
        "questionCount": len(problems), "narrationCount": len(tracks), "verifiedNarrationCount": len(keys),
        "verifiedIds": keys, "collectionCoverageComplete": complete_coverage,
        "entireCollectionValidated": measured and complete_coverage and complete_selection,
        "entireCollectionMetadataValidated": complete_coverage and complete_selection,
        "coverage": coverage_report, "musicCount": 1, "metadataOnly": args.metadata_only,
        "allFilesDecoded": measured and complete_coverage and complete_selection,
        "allSelectedFilesDecoded": measured, "musicDecoded": measured,
        "allScriptAndAudioChecksumsMatch": complete_coverage and complete_selection,
        "allSelectedScriptAndAudioChecksumsMatch": True,
        "actualLoudnessMeasured": measured,
        "checksSkipped": [] if measured else ["full-file-decoding", "waveform-loudness-measurement"] + (["thinking-pause-silence-detection"] if pause_required else []),
        "verificationNote": "已对本次指定范围逐文件完整解码并复测响度。" if measured else "仅检查文件、哈希、编码与响度元数据；未完整解码、未复测波形响度、未验证实际静音。",
        "defaultPlaybackRate": default_rate,
        "totalNarrationMinutes": round(sum(durations) / 60, 2),
        "listeningMinutesAtDefaultRate": round(sum(durations) / 60 / default_rate, 2),
        "shortestNarrationSeconds": min(durations), "longestNarrationSeconds": max(durations),
        "totalNarrationBytes": sum(item["bytes"] for item in results),
        "narrationLufsRange": [min(item["integratedLufs"] for item in results), max(item["integratedLufs"] for item in results)],
        "highestNarrationTruePeakDbtp": max(item["truePeakDbtp"] for item in results),
        "musicSeconds": music["seconds"], "musicLufs": music["lufs"], "musicTruePeakDbtp": music["truePeakDbtp"],
        "separateNarrationAndMusicFiles": True,
        "thinkingPauseVerification": {
            "applicable": pause_required, "enabledCount": pause_count,
            "disabledCount": len(keys) - pause_count if snapshot_path else 0,
            "metadataVerifiedCount": pause_count,
            "waveformVerifiedCount": pause_count if measured else 0,
            "allSelectedPausesVerified": measured if pause_required else None,
            "silenceThresholdDbfs": SILENCE_DBFS, "edgeToleranceSeconds": PAUSE_EDGE_SECONDS,
        },
    }
    if measured:
        report["measuredNarrationLufsRange"] = [min(item["measuredLufs"] for item in results), max(item["measuredLufs"] for item in results)]
        report["highestMeasuredNarrationTruePeakDbtp"] = max(item["measuredTruePeakDbtp"] for item in results)
    if pause_required:
        pause_lengths = [item["pause"][1] for item in pause_results]
        report["thinkingPauseVerification"].update({"sourceDurationRangeSeconds": [min(pause_lengths), max(pause_lengths)], "durationAtDefaultPlaybackRateRangeSeconds": [min(pause_lengths) / default_rate, max(pause_lengths) / default_rate]})
        if measured:
            confirmed = [item["confirmedSilence"][1] - item["confirmedSilence"][0] for item in pause_results]
            report["thinkingPauseVerification"]["confirmedSilenceDurationRangeSeconds"] = [min(confirmed), max(confirmed)]
    if snapshot_path:
        report["sourceSnapshot"] = str(snapshot_path.relative_to(ROOT)) if snapshot_path.is_relative_to(ROOT) else str(snapshot_path)
        report["sourceSnapshotSha256"] = digest(snapshot_path)
        report["sourceDataSha256"] = snapshot.get("sourceDataSha256")
        report["allSelectedSourceChecksumsMatch"] = True
        report["currentPageChanges"] = current_page_changes(collection, problems)
    return report


def main(args):
    try:
        report = validate(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report = {"verifiedAt": datetime.now(timezone.utc).isoformat(), "collection": args.collection, "ok": False, "metadataOnly": args.metadata_only, "validationScope": "selected-ids" if args.ids is not None else "complete-collection", "error": str(error)}
    if args.report:
        path = Path(args.report)
        protected = {ROOT / f"reading/audio/{args.collection}-natural/manifest.json", ROOT / f"scripts/audio/snapshots/{args.collection}-20261015.json"}
        if args.snapshot:
            protected.add(Path(args.snapshot).expanduser().resolve())
        require(path.resolve() not in {value.resolve() for value in protected}, "Report path must not overwrite a manifest or source snapshot")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", choices=list(COLLECTIONS), default="hot100", help="默认验证 hot100")
    parser.add_argument("--snapshot", help="papers 或 bagu 的显式固定快照；默认使用 20261015 快照")
    parser.add_argument("--ids", help="逗号分隔的题号；只验证指定音轨，不要求其余音轨已生成")
    parser.add_argument("--metadata-only", action="store_true", help="不完整解码、不复测响度、不验证实际静音；仍校验文件和哈希")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--report", help="将本集合的 JSON 验证报告保存到指定文件")
    arguments = parser.parse_args()
    if not 1 <= arguments.jobs <= 8:
        parser.error("jobs must be between 1 and 8")
    raise SystemExit(main(arguments))
