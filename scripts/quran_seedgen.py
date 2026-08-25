#!/usr/bin/env python3
"""Generate brainwallet passphrases from Arabic Quran text for brainflayer."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterator

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from seed_variants import expand_variants

DEFAULT_QURAN = Path(__file__).resolve().parent.parent / "data" / "quran_ar.json"

TATWEEL = "\u0640"
QURAN_STOP = "\u06dd"


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_arabic_diacritics(text: str) -> str:
    return "".join(
        ch
        for ch in text
        if unicodedata.category(ch) != "Mn" and ch not in {TATWEEL, QURAN_STOP}
    )


def strip_punctuation(text: str) -> str:
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S"):
            cleaned.append(" ")
        else:
            cleaned.append(char)
    return normalize_ws("".join(cleaned))


def reference_variants(
    surah_num: int,
    ayah_num: int,
    surah_name: str,
    transliteration: str,
) -> list[str]:
    return [
        f"{surah_num}:{ayah_num}",
        f"{surah_num} {ayah_num}",
        f"{surah_num}-{ayah_num}",
        f"Quran {surah_num}:{ayah_num}",
        f"quran {surah_num}:{ayah_num}",
        f"{transliteration} {surah_num}:{ayah_num}",
        f"{transliteration.lower()} {surah_num}:{ayah_num}",
        f"{surah_name} {surah_num}:{ayah_num}",
        f"{surah_name} {surah_num} {ayah_num}",
    ]


def load_quran(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(
            f"Quran data not found at {path}. Run scripts/fetch_quran.py first."
        )
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def iter_ayahs(
    quran: list[dict],
    surahs: set[int] | None = None,
) -> Iterator[tuple[int, int, str, str, str]]:
    for surah in quran:
        surah_num = surah["id"]
        if surahs and surah_num not in surahs:
            continue
        surah_name = surah.get("name", "")
        transliteration = surah.get("transliteration", "")
        for ayah in surah["verses"]:
            yield surah_num, ayah["id"], surah_name, transliteration, ayah["text"]


def generate_candidates(
    quran: list[dict],
    modes: set[str],
    surahs: set[int] | None = None,
    max_words: int = 7,
) -> Iterator[str]:
    seen: set[str] = set()

    def emit(value: str, *, nopunct: str | None = None, nospaces: str | None = None) -> Iterator[str]:
        for candidate in expand_variants(value, nopunct=nopunct, nospaces=nospaces):
            if candidate in seen:
                continue
            seen.add(candidate)
            yield candidate

    for surah_num, ayah_num, surah_name, transliteration, text in iter_ayahs(quran, surahs):
        refs = reference_variants(surah_num, ayah_num, surah_name, transliteration)
        normalized = normalize_ws(text)
        nodiac = normalize_ws(strip_arabic_diacritics(normalized))
        no_spaces = re.sub(r"\s+", "", nodiac)
        nopunct = strip_punctuation(nodiac)
        words = nodiac.split()

        if "reference" in modes:
            for ref in refs:
                yield from emit(ref)

        if "text" in modes:
            yield from emit(normalized, nopunct=nodiac if nodiac != normalized else None)

        if "nodiac" in modes and nodiac:
            yield from emit(nodiac)

        if "nospaces" in modes and no_spaces:
            yield from emit(nodiac, nospaces=no_spaces)

        if "nopunct" in modes and nopunct:
            yield from emit(nodiac, nopunct=nopunct)

        if "ref_text" in modes:
            for ref in refs[:4]:
                for body in (normalized, nodiac):
                    yield from emit(f"{ref} {body}")
                    yield from emit(f"{ref}{body}")
                    yield from emit(f"{body}{ref}")

        if "prefix" in modes and max_words > 0 and words:
            prefix = " ".join(words[:max_words])
            yield from emit(prefix)

        if "bismillah" in modes and surah_num == 1 and ayah_num == 1:
            for phrase in (
                "بسم الله الرحمن الرحيم",
                "بسم الله",
                "bismillah",
                "Bismillah",
            ):
                yield from emit(phrase)


def parse_int_set(raw: str | None) -> set[int] | None:
    if not raw:
        return None
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes (default: all):
  reference   Surah:ayah references (2:255, Quran 2:255, Arabic surah name variants)
  text        Full ayah text (Uthmani and without diacritics)
  nodiac      Ayah text with Arabic diacritics removed
  nospaces    Diacritic-stripped text with spaces removed
  nopunct     Diacritic-stripped text with punctuation removed
  ref_text    Reference concatenated with ayah text
  prefix      First N words of each ayah (use --max-words)
  bismillah   Common standalone Bismillah variants

Examples:
  python3 scripts/quran_seedgen.py | ./brainflayer -v -b data/btc.blf
  python3 scripts/quran_seedgen.py --surah 2 --limit 50
        """,
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_QURAN,
        help=f"Arabic Quran JSON file (default: {DEFAULT_QURAN})",
    )
    parser.add_argument(
        "--modes",
        default="reference,text,nodiac,nospaces,nopunct,ref_text,prefix,bismillah",
        help="Comma-separated generation modes",
    )
    parser.add_argument(
        "--surah",
        action="append",
        dest="surahs",
        help="Limit to surah number(s); repeatable or comma-separated (1-114)",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=7,
        help="Word count for prefix mode (default: 7)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after emitting N candidates (0 = unlimited)",
    )
    args = parser.parse_args()

    quran = load_quran(args.input)
    modes = {part.strip() for part in args.modes.split(",") if part.strip()}
    if not modes:
        raise SystemExit("At least one mode is required.")

    surah_filter: set[int] = set()
    if args.surahs:
        for entry in args.surahs:
            surah_filter.update(parse_int_set(entry) or set())

    count = 0
    for candidate in generate_candidates(
        quran,
        modes=modes,
        surahs=surah_filter or None,
        max_words=args.max_words,
    ):
        print(candidate)
        count += 1
        if args.limit and count >= args.limit:
            break

    print(f"Emitted {count:,} candidates", file=sys.stderr)


if __name__ == "__main__":
    main()
