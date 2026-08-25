#!/usr/bin/env python3
"""Download Arabic Quran text (Uthmani) for brainflayer seed generation."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://cdn.jsdelivr.net/npm/quran-json@3.1.2/dist/quran.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "quran_ar.json"


def fetch(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Fetching Arabic Quran from {url}", file=sys.stderr)
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to download Quran text: {exc}") from exc

    quran = json.loads(data.decode("utf-8"))
    if not isinstance(quran, list) or not quran or "verses" not in quran[0]:
        raise SystemExit("Downloaded file does not look like valid quran-json data.")

    output.write_bytes(data)
    surahs = len(quran)
    ayahs = sum(len(surah["verses"]) for surah in quran)
    print(
        f"Saved {surahs} surahs, {ayahs} ayahs to {output} "
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
        help="Arabic Quran JSON source URL",
    )
    args = parser.parse_args()
    fetch(args.url, args.output)


if __name__ == "__main__":
    main()
