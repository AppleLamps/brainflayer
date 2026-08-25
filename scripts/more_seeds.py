#!/usr/bin/env python3
"""Fetch new public corpora and emit seed candidates not already tested."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from dict_phrases import iter_dictionary_phrases
from seed_variants import expand_variants

CORPORA = ROOT / "data" / "corpora"
EXISTING = ROOT / "data" / "seed_candidates.txt"
DELTA = ROOT / "data" / "seed_candidates_delta.txt"
UA = "brainflayer-seedgen/1.0"

FREQ_LANGS = {
    "fr": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/fr/fr_50k.txt",
    "es": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/es/es_50k.txt",
    "de": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/de/de_50k.txt",
    "it": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/it/it_50k.txt",
    "pt": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/pt_br/pt_br_50k.txt",
    "nl": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/nl/nl_50k.txt",
    "pl": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/pl/pl_50k.txt",
    "tr": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/tr/tr_50k.txt",
    "id": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/id/id_50k.txt",
    "sv": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/sv/sv_50k.txt",
    "uk": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/uk/uk_50k.txt",
    "ro": "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/ro/ro_50k.txt",
}

DOWNLOADS: dict[str, str] = {
    "passwords_100k.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/xato-net-10-million-passwords-100000.txt"
    ),
    "passwords_1m.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt"
    ),
    "passwords_10k.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/10k-most-common.txt"
    ),
    "passwords_darkweb.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/darkweb2017-top10000.txt"
    ),
    "passwords_rockyou75.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Leaked-Databases/rockyou-75.txt"
    ),
    "quran_en_pickthall.txt": "https://tanzil.net/trans/en.pickthall",
    "quran_en_yusufali.txt": "https://tanzil.net/trans/en.yusufali",
    "bible_bbe.json": (
        "https://raw.githubusercontent.com/thiagobodruk/bible/master/json/en_bbe.json"
    ),
    "quotes.json": (
        "https://raw.githubusercontent.com/dwyl/quotes/main/quotes.json"
    ),
    "quotes2.json": (
        "https://raw.githubusercontent.com/JamesFT/Database-Quotes-JSON/master/quotes.json"
    ),
    "first_names.txt": (
        "https://raw.githubusercontent.com/dominictarr/random-name/master/first-names.txt"
    ),
    "last_names.txt": (
        "https://raw.githubusercontent.com/dominictarr/random-name/master/names.txt"
    ),
    "countries.csv": (
        "https://raw.githubusercontent.com/datasets/country-list/master/data.csv"
    ),
    "bip39_en.txt": (
        "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt"
    ),
    "alice.txt": "https://www.gutenberg.org/files/11/11-0.txt",
    "shakespeare.txt": "https://www.gutenberg.org/files/100/100-0.txt",
    "artofwar.txt": "https://www.gutenberg.org/files/132/132-0.txt",
    "taoteching.txt": "https://www.gutenberg.org/files/216/216.txt",
    "constitution.txt": "https://www.gutenberg.org/files/5/5-0.txt",
    "gettysburg.txt": "https://www.gutenberg.org/files/4/4-0.txt",
    "moby.txt": "https://www.gutenberg.org/files/2701/2701-0.txt",
}

EXTRA_PHRASES = [
    "to be or not to be",
    "that is the question",
    "may the force be with you",
    "live long and prosper",
    "winter is coming",
    "i am your father",
    "one ring to rule them all",
    "all your base are belong to us",
    "the cake is a lie",
    "never gonna give you up",
    "show me the money",
    "hasta la vista baby",
    "i'll be back",
    "houston we have a problem",
    "that's one small step for man",
    "one small step for man",
    "i have a dream",
    "ask not what your country can do for you",
    "four score and seven years ago",
    "we the people",
    "when in the course of human events",
    "e pluribus unum",
    "annuit coeptis",
    "novus ordo seclorum",
    "don't panic",
    "so long and thanks for all the fish",
    "not your keys not your coins",
    "buy bitcoin",
    "stack sats",
    "digital gold",
    "peer to peer electronic cash",
    "a purely peer-to-peer version of electronic cash",
    "proof of work",
    "21 million",
    "end the fed",
    "number go up",
    "have fun staying poor",
    "few understand",
    "orange pill",
    "honey badger don't care",
    "andreas antonopoulos",
    "nick szabo",
    "hal finney",
    "running bitcoin",
    "dorian nakamoto",
    "bitcoin pizza",
    "two pizzas",
    "10000 bitcoin",
    "silk road",
    "ross ulbricht",
    "mtgox",
    "mark karpeles",
    "p2p foundation",
    "cryptography mailing list",
    "double-spending",
    "timestamp server",
    "longest chain",
    "honest nodes",
    "cpu voting",
    "letmein",
    "trustno1",
    "qwerty",
    "abc123",
    "iloveyou",
    "monkey",
    "dragon",
    "master",
    "shadow",
    "michael",
    "jennifer",
    "hunter2",
    "correct horse",
    "battery staple",
    "wikileaks",
    "free ross",
    "free the silk road",
    "in cryptography we trust",
    "vires in numeris",
    "the times 03/jan/2009",
    "chancellor on brink of second bailout for banks",
]

BBE_ABBREV = {
    "gn": "Genesis",
    "ex": "Exodus",
    "lv": "Leviticus",
    "nm": "Numbers",
    "dt": "Deuteronomy",
    "js": "Joshua",
    "jud": "Judges",
    "rt": "Ruth",
    "1sm": "1 Samuel",
    "2sm": "2 Samuel",
    "1kgs": "1 Kings",
    "2kgs": "2 Kings",
    "1ch": "1 Chronicles",
    "2ch": "2 Chronicles",
    "ezr": "Ezra",
    "ne": "Nehemiah",
    "et": "Esther",
    "job": "Job",
    "ps": "Psalms",
    "prv": "Proverbs",
    "ec": "Ecclesiastes",
    "so": "Song of Solomon",
    "is": "Isaiah",
    "jr": "Jeremiah",
    "lm": "Lamentations",
    "ez": "Ezekiel",
    "dn": "Daniel",
    "ho": "Hosea",
    "jl": "Joel",
    "am": "Amos",
    "ob": "Obadiah",
    "jn": "Jonah",
    "mi": "Micah",
    "na": "Nahum",
    "hk": "Habakkuk",
    "zp": "Zephaniah",
    "hg": "Haggai",
    "zc": "Zechariah",
    "ml": "Malachi",
    "mt": "Matthew",
    "mk": "Mark",
    "lk": "Luke",
    "jo": "John",
    "act": "Acts",
    "rm": "Romans",
    "1co": "1 Corinthians",
    "2co": "2 Corinthians",
    "gl": "Galatians",
    "eph": "Ephesians",
    "ph": "Philippians",
    "cl": "Colossians",
    "1ts": "1 Thessalonians",
    "2ts": "2 Thessalonians",
    "1tm": "1 Timothy",
    "2tm": "2 Timothy",
    "tt": "Titus",
    "phm": "Philemon",
    "hb": "Hebrews",
    "jm": "James",
    "1pe": "1 Peter",
    "2pe": "2 Peter",
    "1jo": "1 John",
    "2jo": "2 John",
    "3jo": "3 John",
    "jd": "Jude",
    "re": "Revelation",
}

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def fetch_file(name: str, url: str) -> Path | None:
    dest = CORPORA / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 100:
        print(f"  cached {name} ({dest.stat().st_size:,} bytes)", file=sys.stderr)
        return dest
    print(f"  fetching {name} ...", file=sys.stderr)
    try:
        data = download(url)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(f"  SKIP {name}: {exc}", file=sys.stderr)
        return None
    if len(data) < 50:
        print(f"  SKIP {name}: too small ({len(data)} bytes)", file=sys.stderr)
        return None
    dest.write_bytes(data)
    print(f"  saved {name} ({dest.stat().st_size:,} bytes)", file=sys.stderr)
    return dest


def fetch_all() -> None:
    print("Fetching new corpora...", file=sys.stderr)
    for name, url in DOWNLOADS.items():
        fetch_file(name, url)
    for lang, url in FREQ_LANGS.items():
        fetch_file(f"freq_{lang}.txt", url)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_punctuation(text: str) -> str:
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S"):
            cleaned.append(" ")
        else:
            cleaned.append(char)
    return normalize_ws("".join(cleaned))


def gutenberg_body(raw: str) -> str:
    start = re.search(r"\*\*\*\s*START OF.+\*\*\*", raw, flags=re.I)
    end = re.search(r"\*\*\*\s*END OF.+\*\*\*", raw, flags=re.I)
    if start and end and end.start() > start.end():
        return raw[start.end() : end.start()]
    return raw


def iter_sentences(text: str) -> list[str]:
    body = gutenberg_body(text)
    sentences: list[str] = []
    for chunk in SENTENCE_SPLIT.split(body.replace("\r\n", "\n").replace("\r", "\n")):
        line = normalize_ws(chunk.replace("\n", " "))
        if 12 <= len(line) <= 180:
            words = WORD_RE.findall(line)
            if 3 <= len(words) <= 24:
                sentences.append(line)
    return sentences


def load_freq_words(path: Path, limit: int = 20000) -> list[str]:
    words: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            word = line.split()[0].strip() if line.strip() else ""
            if len(word) < 2 or word in seen:
                continue
            seen.add(word)
            words.append(word)
            if len(words) >= limit:
                break
    return words


def load_password_lines(path: Path, limit: int | None = None) -> list[str]:
    lines: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            item = line.strip()
            if 3 <= len(item) <= 128:
                lines.append(item)
                if limit is not None and len(lines) >= limit:
                    break
    return lines


def load_tanzil_ayahs(path: Path) -> list[tuple[int, int, str]]:
    ayahs: list[tuple[int, int, str]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("|", 2)
            if len(parts) != 3:
                continue
            try:
                surah, ayah = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            text = normalize_ws(parts[2])
            if text:
                ayahs.append((surah, ayah, text))
    return ayahs


def load_bbe_verses(path: Path) -> list[tuple[str, int, int, str]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    verses: list[tuple[str, int, int, str]] = []
    if not isinstance(payload, list):
        return verses
    for book in payload:
        abbrev = str(book.get("abbrev", "")).lower()
        book_name = BBE_ABBREV.get(abbrev, abbrev.title() or "Book")
        chapters = book.get("chapters") or []
        for chapter_idx, chapter in enumerate(chapters, start=1):
            if not isinstance(chapter, list):
                continue
            for verse_idx, text in enumerate(chapter, start=1):
                cleaned = normalize_ws(str(text))
                if cleaned:
                    verses.append((book_name, chapter_idx, verse_idx, cleaned))
    return verses


def load_quotes(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            payload = json.loads(path.read_text(encoding="latin-1"))
        except json.JSONDecodeError:
            return []
    quotes: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                quotes.append(normalize_ws(item))
            elif isinstance(item, dict):
                for key in ("quote", "text", "quoteText", "body"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        quotes.append(normalize_ws(value))
                        break
    return [q for q in quotes if 8 <= len(q) <= 240]


def load_names(path: Path, limit: int = 3000) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            name = line.strip().strip('"')
            if not name or name.lower() in seen or not re.fullmatch(r"[A-Za-z][A-Za-z'\-]{1,30}", name):
                continue
            seen.add(name.lower())
            names.append(name)
            if len(names) >= limit:
                break
    return names


def load_countries(path: Path) -> list[str]:
    names: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("Name") or row.get("name") or "").strip()
            if name:
                names.append(name)
    return names


class Emitter:
    def __init__(self, existing: set[int], handle: io.TextIOBase) -> None:
        self.existing = existing
        self.handle = handle
        self.written = 0
        self.skipped = 0
        self.by_source: dict[str, int] = {}

    def emit(self, source: str, value: str, *, nopunct: bool = True) -> None:
        base = normalize_ws(value)
        if not base:
            return
        extra = strip_punctuation(base) if nopunct else None
        for variant in expand_variants(base, nopunct=extra):
            digest = hash(variant.encode("utf-8"))
            if digest in self.existing:
                self.skipped += 1
                continue
            self.existing.add(digest)
            self.handle.write(variant + "\n")
            self.written += 1
            self.by_source[source] = self.by_source.get(source, 0) + 1


def load_existing_hashes(path: Path) -> set[int]:
    seen: set[int] = set()
    if not path.exists():
        print(f"No existing seed file at {path}; treating all as new.", file=sys.stderr)
        return seen
    print(f"Indexing already-tested seeds from {path} ...", file=sys.stderr)
    with path.open("rb") as handle:
        for index, line in enumerate(handle, start=1):
            seen.add(hash(line.rstrip(b"\n\r")))
            if index % 5_000_000 == 0:
                print(f"  hashed {index:,} existing lines", file=sys.stderr)
    print(f"  {len(seen):,} existing hashes loaded", file=sys.stderr)
    return seen


def emit_scripture_verse(
    emitter: Emitter,
    source: str,
    book: str,
    chapter: int,
    verse: int,
    text: str,
) -> None:
    refs = [
        f"{book} {chapter}:{verse}",
        f"{book} {chapter}:{verse} {text}",
        f"{book} {chapter} {verse}",
        text,
    ]
    for ref in refs:
        emitter.emit(source, ref)
    words = strip_punctuation(text).split()
    if words:
        prefix = " ".join(words[:7])
        emitter.emit(source, prefix)


def generate(emitter: Emitter) -> None:
    print("Generating new seed candidates...", file=sys.stderr)

    for phrase in EXTRA_PHRASES:
        emitter.emit("extra", phrase)

    for year in range(1970, 2017):
        emitter.emit("year", str(year), nopunct=False)
        emitter.emit("year", f"bitcoin {year}")
        emitter.emit("year", f"password{year}", nopunct=False)

    for name in ("passwords_10k.txt", "passwords_100k.txt", "passwords_1m.txt", "passwords_darkweb.txt", "passwords_rockyou75.txt"):
        path = CORPORA / name
        if not path.exists():
            continue
        print(f"  passwords {name}...", file=sys.stderr)
        for password in load_password_lines(path):
            emitter.emit("password", password, nopunct=False)

    for lang in FREQ_LANGS:
        path = CORPORA / f"freq_{lang}.txt"
        if not path.exists():
            continue
        words = load_freq_words(path, limit=20000)
        print(f"  {lang} dictionary {len(words):,} words...", file=sys.stderr)
        for word in words:
            emitter.emit(f"dict:{lang}", word, nopunct=False)
        print(f"  {lang} 2-3 word phrases...", file=sys.stderr)
        for phrase in iter_dictionary_phrases(
            words,
            phrase_lengths=(2, 3),
            top_n_by_length={2: 250, 3: 40},
        ):
            emitter.emit(f"dict:{lang}:phrase", phrase, nopunct=False)

    for name, source in (
        ("quran_en_pickthall.txt", "quran-en-pickthall"),
        ("quran_en_yusufali.txt", "quran-en-yusufali"),
    ):
        path = CORPORA / name
        if not path.exists():
            continue
        ayahs = load_tanzil_ayahs(path)
        print(f"  {source} {len(ayahs):,} ayahs...", file=sys.stderr)
        for surah, ayah, text in ayahs:
            emit_scripture_verse(emitter, source, "Quran", surah, ayah, text)
            emitter.emit(source, f"{surah}:{ayah} {text}")

    bbe_path = CORPORA / "bible_bbe.json"
    if bbe_path.exists():
        verses = load_bbe_verses(bbe_path)
        print(f"  BBE bible {len(verses):,} verses...", file=sys.stderr)
        for book, chapter, verse, text in verses:
            emit_scripture_verse(emitter, "bible-bbe", book, chapter, verse, text)

    for name in ("quotes.json", "quotes2.json"):
        path = CORPORA / name
        if not path.exists():
            continue
        quotes = load_quotes(path)
        print(f"  {name} {len(quotes):,} quotes...", file=sys.stderr)
        for quote in quotes:
            emitter.emit("quote", quote)

    firsts = load_names(CORPORA / "first_names.txt") if (CORPORA / "first_names.txt").exists() else []
    lasts = load_names(CORPORA / "last_names.txt") if (CORPORA / "last_names.txt").exists() else []
    if firsts:
        print(f"  names {len(firsts)} first / {len(lasts)} last...", file=sys.stderr)
        for name in firsts[:2500]:
            emitter.emit("name", name, nopunct=False)
        for name in lasts[:2500]:
            emitter.emit("name", name, nopunct=False)
        for first in firsts[:120]:
            for last in lasts[:120]:
                emitter.emit("name", f"{first} {last}")

    countries_path = CORPORA / "countries.csv"
    if countries_path.exists():
        for country in load_countries(countries_path):
            emitter.emit("geo", country)
            emitter.emit("geo", f"bitcoin {country}")

    bip39_path = CORPORA / "bip39_en.txt"
    if bip39_path.exists():
        words = load_password_lines(bip39_path)
        print(f"  BIP39 {len(words)} words...", file=sys.stderr)
        for word in words:
            emitter.emit("bip39", word, nopunct=False)
        for phrase in iter_dictionary_phrases(
            words,
            phrase_lengths=(2, 3, 4),
            top_n_by_length={2: 200, 3: 50, 4: 20},
        ):
            emitter.emit("bip39:phrase", phrase, nopunct=False)

    for name in (
        "alice.txt",
        "shakespeare.txt",
        "artofwar.txt",
        "taoteching.txt",
        "constitution.txt",
        "gettysburg.txt",
        "moby.txt",
    ):
        path = CORPORA / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        sentences = iter_sentences(text)
        print(f"  {name} {len(sentences):,} sentences...", file=sys.stderr)
        # Cap very large books so we keep famous/early lines plus a tail sample.
        if len(sentences) > 8000:
            sentences = sentences[:5000] + sentences[len(sentences) // 2 : len(sentences) // 2 + 1500]
        for sentence in sentences:
            emitter.emit("book", sentence)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-fetch", action="store_true", help="Use already-downloaded corpora")
    parser.add_argument(
        "--existing",
        type=Path,
        default=EXISTING,
        help="Already-tested seed file to exclude",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DELTA,
        help="New-only seed output",
    )
    args = parser.parse_args()

    if not args.skip_fetch:
        fetch_all()

    existing = load_existing_hashes(args.existing)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        emitter = Emitter(existing, handle)
        generate(emitter)

    print(f"Wrote {emitter.written:,} NEW candidates -> {args.output}", file=sys.stderr)
    print(f"Skipped {emitter.skipped:,} already-tested variants", file=sys.stderr)
    for source, count in sorted(emitter.by_source.items(), key=lambda item: -item[1]):
        print(f"  {source}: {count:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
