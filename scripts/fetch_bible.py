#!/usr/bin/env python3
"""Download public-domain KJV Bible text for brainflayer seed generation."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = (
    "https://raw.githubusercontent.com/midvash/bible-data/main/versions/en/kjv/kjv.json"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "kjv.json"


def fetch(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching KJV Bible from {url}", file=sys.stderr)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to download Bible text: {exc}") from exc

    bible = json.loads(data.decode("utf-8"))
    if "books" not in bible or not bible["books"]:
        raise SystemExit("Downloaded file does not look like a valid KJV JSON Bible.")

    output.write_bytes(data)
    book_count = len(bible["books"])
    verse_count = sum(
        len(chapter["verses"])
        for book in bible["books"]
        for chapter in book["chapters"]
    )
    print(
        f"Saved {book_count} books, {verse_count} verses to {output} "
        f"({output.stat().st_size:,} bytes)",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-u",
        "--url",
        default=DEFAULT_URL,
        help="KJV JSON source URL",
    )
    args = parser.parse_args()
    fetch(args.url, args.output)


if __name__ == "__main__":
    main()
