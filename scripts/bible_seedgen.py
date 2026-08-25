#!/usr/bin/env python3
"""Generate brainwallet passphrases from Bible text for brainflayer."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, Iterator

DEFAULT_BIBLE = Path(__file__).resolve().parent.parent / "data" / "kjv.json"

BOOK_ALIASES = {
    "genesis": "Genesis",
    "gen": "Genesis",
    "exodus": "Exodus",
    "exod": "Exodus",
    "ex": "Exodus",
    "leviticus": "Leviticus",
    "lev": "Leviticus",
    "numbers": "Numbers",
    "num": "Numbers",
    "deuteronomy": "Deuteronomy",
    "deut": "Deuteronomy",
    "dt": "Deuteronomy",
    "joshua": "Joshua",
    "josh": "Joshua",
    "judges": "Judges",
    "judg": "Judges",
    "ruth": "Ruth",
    "1samuel": "1 Samuel",
    "1sam": "1 Samuel",
    "2samuel": "2 Samuel",
    "2sam": "2 Samuel",
    "1kings": "1 Kings",
    "1kgs": "1 Kings",
    "2kings": "2 Kings",
    "2kgs": "2 Kings",
    "1chronicles": "1 Chronicles",
    "1chr": "1 Chronicles",
    "2chronicles": "2 Chronicles",
    "2chr": "2 Chronicles",
    "ezra": "Ezra",
    "nehemiah": "Nehemiah",
    "neh": "Nehemiah",
    "esther": "Esther",
    "esth": "Esther",
    "job": "Job",
    "psalm": "Psalms",
    "psalms": "Psalms",
    "ps": "Psalms",
    "proverbs": "Proverbs",
    "prov": "Proverbs",
    "ecclesiastes": "Ecclesiastes",
    "eccl": "Ecclesiastes",
    "songofsolomon": "Song of Solomon",
    "song": "Song of Solomon",
    "isaiah": "Isaiah",
    "isa": "Isaiah",
    "jeremiah": "Jeremiah",
    "jer": "Jeremiah",
    "lamentations": "Lamentations",
    "lam": "Lamentations",
    "ezekiel": "Ezekiel",
    "ezek": "Ezekiel",
    "daniel": "Daniel",
    "dan": "Daniel",
    "hosea": "Hosea",
    "hos": "Hosea",
    "joel": "Joel",
    "amos": "Amos",
    "obadiah": "Obadiah",
    "obad": "Obadiah",
    "jonah": "Jonah",
    "micah": "Micah",
    "mic": "Micah",
    "nahum": "Nahum",
    "nah": "Nahum",
    "habakkuk": "Habakkuk",
    "hab": "Habakkuk",
    "zephaniah": "Zephaniah",
    "zeph": "Zephaniah",
    "haggai": "Haggai",
    "hag": "Haggai",
    "zechariah": "Zechariah",
    "zech": "Zechariah",
    "malachi": "Malachi",
    "mal": "Malachi",
    "matthew": "Matthew",
    "matt": "Matthew",
    "mt": "Matthew",
    "mark": "Mark",
    "mk": "Mark",
    "luke": "Luke",
    "lk": "Luke",
    "john": "John",
    "jn": "John",
    "acts": "Acts",
    "romans": "Romans",
    "rom": "Romans",
    "1corinthians": "1 Corinthians",
    "1cor": "1 Corinthians",
    "2corinthians": "2 Corinthians",
    "2cor": "2 Corinthians",
    "galatians": "Galatians",
    "gal": "Galatians",
    "ephesians": "Ephesians",
    "eph": "Ephesians",
    "philippians": "Philippians",
    "phil": "Philippians",
    "colossians": "Colossians",
    "col": "Colossians",
    "1thessalonians": "1 Thessalonians",
    "1thess": "1 Thessalonians",
    "2thessalonians": "2 Thessalonians",
    "2thess": "2 Thessalonians",
    "1timothy": "1 Timothy",
    "1tim": "1 Timothy",
    "2timothy": "2 Timothy",
    "2tim": "2 Timothy",
    "titus": "Titus",
    "tit": "Titus",
    "philemon": "Philemon",
    "phlm": "Philemon",
    "hebrews": "Hebrews",
    "heb": "Hebrews",
    "james": "James",
    "jas": "James",
    "1peter": "1 Peter",
    "1pet": "1 Peter",
    "2peter": "2 Peter",
    "2pet": "2 Peter",
    "1john": "1 John",
    "1jn": "1 John",
    "2john": "2 John",
    "2jn": "2 John",
    "3john": "3 John",
    "3jn": "3 John",
    "jude": "Jude",
    "revelation": "Revelation",
    "rev": "Revelation",
}


def normalize_book_name(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return BOOK_ALIASES.get(key, name)


def strip_punctuation(text: str) -> str:
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S"):
            cleaned.append(" ")
        else:
            cleaned.append(char)
    return re.sub(r"\s+", " ", "".join(cleaned)).strip()


def compact_book_name(book: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", book)


def reference_variants(book: str, chapter: int, verse: int) -> list[str]:
    compact = compact_book_name(book)
    spaced = f"{book} {chapter}:{verse}"
    return [
        spaced,
        spaced.lower(),
        spaced.upper(),
        f"{compact}{chapter}:{verse}",
        f"{compact.lower()}{chapter}:{verse}",
        f"{compact}{chapter}{verse}",
        f"{compact.lower()}{chapter}{verse}",
        f"{book} {chapter} {verse}",
        f"{book} {chapter}-{verse}",
    ]


def load_bible(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Bible data not found at {path}. Run scripts/fetch_bible.py first."
        )
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def iter_verses(
    bible: dict,
    books: set[str] | None = None,
    chapters: set[int] | None = None,
) -> Iterator[tuple[str, int, int, str]]:
    for book in bible["books"]:
        book_name = book["book"]
        if books and book_name not in books:
            continue
        for chapter in book["chapters"]:
            chapter_num = chapter["chapter"]
            if chapters and chapter_num not in chapters:
                continue
            for verse in chapter["verses"]:
                yield book_name, chapter_num, verse["number"], verse["text"]


def generate_candidates(
    bible: dict,
    modes: set[str],
    books: set[str] | None = None,
    chapters: set[int] | None = None,
    max_words: int = 0,
) -> Iterator[str]:
    seen: set[str] = set()

    def emit(value: str) -> Iterator[str]:
        candidate = value.strip()
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        yield candidate

    for book, chapter, verse_num, text in iter_verses(bible, books, chapters):
        refs = reference_variants(book, chapter, verse_num)
        normalized = re.sub(r"\s+", " ", text).strip()
        lower = normalized.lower()
        upper = normalized.upper()
        no_punct = strip_punctuation(normalized)
        no_punct_lower = no_punct.lower()
        no_spaces = re.sub(r"\s+", "", no_punct)
        no_spaces_lower = no_spaces.lower()
        words = no_punct.split()

        if "reference" in modes:
            for ref in refs:
                yield from emit(ref)

        if "text" in modes:
            for candidate in (normalized, lower, upper):
                yield from emit(candidate)

        if "nopunct" in modes:
            for candidate in (no_punct, no_punct_lower):
                yield from emit(candidate)

        if "nospaces" in modes:
            for candidate in (no_spaces, no_spaces_lower):
                yield from emit(candidate)

        if "ref_text" in modes:
            for ref in refs[:3]:
                for body in (normalized, lower, no_punct_lower):
                    yield from emit(f"{ref} {body}")
                    yield from emit(f"{ref}{body}")
                    yield from emit(body + ref)

        if "words" in modes:
            for word in words:
                if len(word) >= 3:
                    yield from emit(word)
                    yield from emit(word.lower())

        if "prefix" in modes and max_words > 0:
            prefix = " ".join(words[:max_words])
            if prefix:
                yield from emit(prefix)
                yield from emit(prefix.lower())
                yield from emit(strip_punctuation(prefix).lower())


def parse_books(raw: str | None) -> set[str] | None:
    if not raw:
        return None
    return {normalize_book_name(part.strip()) for part in raw.split(",") if part.strip()}


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
  reference   Book/chapter/verse reference strings (John 3:16, john3:16, ...)
  text        Full verse text (original, lower, upper)
  nopunct     Verse text with punctuation removed
  nospaces    Verse text with spaces and punctuation removed
  ref_text    Reference concatenated with verse text
  words       Individual words from each verse (3+ chars)
  prefix      First N words of each verse (use --max-words)

Examples:
  python3 scripts/bible_seedgen.py | ./brainflayer -v -b example.blf
  python3 scripts/bible_seedgen.py --book John --chapter 3 --limit 100
  python3 scripts/bible_seedgen.py --modes reference,text --book "1 Corinthians"
        """,
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=DEFAULT_BIBLE,
        help=f"KJV JSON file (default: {DEFAULT_BIBLE})",
    )
    parser.add_argument(
        "--modes",
        default="reference,text,nopunct,nospaces,ref_text,words,prefix",
        help="Comma-separated generation modes",
    )
    parser.add_argument(
        "--book",
        action="append",
        dest="books",
        help="Limit to book(s); repeatable or comma-separated",
    )
    parser.add_argument(
        "--chapter",
        action="append",
        dest="chapters",
        help="Limit to chapter number(s); repeatable or comma-separated",
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

    bible = load_bible(args.input)
    modes = {part.strip() for part in args.modes.split(",") if part.strip()}
    if not modes:
        raise SystemExit("At least one mode is required.")

    book_filter: set[str] = set()
    if args.books:
        for entry in args.books:
            book_filter.update(parse_books(entry) or set())
    chapter_filter: set[int] = set()
    if args.chapters:
        for entry in args.chapters:
            chapter_filter.update(parse_int_set(entry) or set())

    count = 0
    for candidate in generate_candidates(
        bible,
        modes=modes,
        books=book_filter or None,
        chapters=chapter_filter or None,
        max_words=args.max_words,
    ):
        print(candidate)
        count += 1
        if args.limit and count >= args.limit:
            break

    print(f"Emitted {count:,} candidates", file=sys.stderr)


if __name__ == "__main__":
    main()
