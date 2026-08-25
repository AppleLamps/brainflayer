#!/usr/bin/env python3
"""Download English, Russian, and Chinese dictionary word lists."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DICT_DIR = ROOT / "data" / "dict"

SOURCES = {
    "en": {
        "url": "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt",
        "output": DICT_DIR / "english.txt",
    },
    "ru": {
        "url": "https://raw.githubusercontent.com/hingston/russian/master/100000-russian-words.txt",
        "output": DICT_DIR / "russian.txt",
    },
    "zh": {
        "url": "https://raw.githubusercontent.com/drkameleon/complete-hsk-vocabulary/master/complete.json",
        "output": DICT_DIR / "chinese.json",
        "words_output": DICT_DIR / "chinese.txt",
    },
}

CYRILLIC_RE = re.compile(r"^[А-Яа-яЁё\-]+$")
CJK_RE = re.compile(r"^[\u4e00-\u9fff]+$")
EN_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def download(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=180) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to download {url}: {exc}") from exc


def clean_english(raw: bytes) -> list[str]:
    words = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        word = line.strip()
        if len(word) >= 3 and EN_RE.fullmatch(word):
            words.append(word)
    return sorted(set(words))


def clean_russian(raw: bytes) -> list[str]:
    words = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        word = line.strip()
        if len(word) >= 2 and CYRILLIC_RE.fullmatch(word):
            words.append(word)
    return sorted(set(words))


def clean_chinese(raw: bytes) -> tuple[list[str], bytes]:
    payload = json.loads(raw.decode("utf-8"))
    words: set[str] = set()
    for entry in payload:
        simplified = entry.get("simplified", "").strip()
        if simplified and CJK_RE.fullmatch(simplified):
            words.add(simplified)
        for form in entry.get("forms", []):
            traditional = form.get("traditional", "").strip()
            if traditional and CJK_RE.fullmatch(traditional):
                words.add(traditional)
    word_list = sorted(words)
    return word_list, raw


def fetch_language(language: str) -> None:
    spec = SOURCES[language]
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {language} dictionary from {spec['url']}", file=sys.stderr)
    raw = download(spec["url"])

    if language == "en":
        words = clean_english(raw)
        spec["output"].write_text("\n".join(words) + "\n", encoding="utf-8")
    elif language == "ru":
        words = clean_russian(raw)
        spec["output"].write_text("\n".join(words) + "\n", encoding="utf-8")
    elif language == "zh":
        words, raw = clean_chinese(raw)
        spec["output"].write_bytes(raw)
        spec["words_output"].write_text("\n".join(words) + "\n", encoding="utf-8")
        print(
            f"Saved {len(words):,} Chinese words -> {spec['words_output']} "
            f"({spec['words_output'].stat().st_size:,} bytes)",
            file=sys.stderr,
        )
        return
    else:
        raise SystemExit(f"Unsupported language: {language}")

    print(
        f"Saved {len(words):,} {language} words -> {spec['output']} "
        f"({spec['output'].stat().st_size:,} bytes)",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--lang",
        choices=["en", "ru", "zh", "all"],
        default="all",
        help="Which dictionary to fetch (default: all)",
    )
    args = parser.parse_args()
    languages = ["en", "ru", "zh"] if args.lang == "all" else [args.lang]
    for language in languages:
        fetch_language(language)


if __name__ == "__main__":
    main()
