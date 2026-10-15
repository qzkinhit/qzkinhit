#!/usr/bin/env python3
"""Capture the current paper or interview cards as a fixed audio production batch."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PAGES = {"papers": "10-papers.html", "bagu": "11-bagu.html"}


def capture(collection):
    path = ROOT / "reading" / PAGES[collection]
    match = re.search(r'<script type="application/json" id="data">(.*?)</script>', path.read_text(), re.S)
    if not match:
        raise ValueError(f"Question data not found in {path}")
    data = json.loads(match.group(1))
    cards = {}
    if collection == "papers":
        for paper in data:
            for position, card in enumerate(paper["cards"], 1):
                key = f"{paper['id']}-{position}"
                if key in cards:
                    raise ValueError(f"Duplicate card ID {key}")
                cards[key] = {"id": key, "title": card["q"], "group": paper["name"], "groupId": paper["id"], "source": card}
    else:
        for card in data["cards"]:
            key = card["id"]
            if key in cards:
                raise ValueError(f"Duplicate card ID {key}")
            cards[key] = {"id": key, "title": card["q"], "group": card.get("topic", "八股"), "source": card}
    return {
        "schemaVersion": 1, "collection": collection, "sourcePage": str(path.relative_to(ROOT)),
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "sourceDataSha256": hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "count": len(cards), "cards": cards,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", choices=PAGES, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New snapshot path; use a new filename to retain previous batches")
    parser.add_argument("--force", action="store_true", help="Explicitly allow replacing an existing snapshot")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        parser.error("The snapshot already exists; choose a new path or explicitly use --force")
    snapshot = capture(args.collection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w" if args.force else "x") as stream:
        stream.write(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print(f"Captured {snapshot['count']} {args.collection} cards in {args.output}")
