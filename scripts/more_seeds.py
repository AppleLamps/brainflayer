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


def _freq_url(lang: str, filename: str) -> str:
    return (
        "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/"
        f"content/2018/{lang}/{filename}"
    )


# Already-tested in the first extra-corpora run: fr es de it pt nl pl tr id sv uk ro
FREQ_LANGS = {
    "fr": _freq_url("fr", "fr_50k.txt"),
    "es": _freq_url("es", "es_50k.txt"),
    "de": _freq_url("de", "de_50k.txt"),
    "it": _freq_url("it", "it_50k.txt"),
    "pt": _freq_url("pt_br", "pt_br_50k.txt"),
    "nl": _freq_url("nl", "nl_50k.txt"),
    "pl": _freq_url("pl", "pl_50k.txt"),
    "tr": _freq_url("tr", "tr_50k.txt"),
    "id": _freq_url("id", "id_50k.txt"),
    "sv": _freq_url("sv", "sv_50k.txt"),
    "uk": _freq_url("uk", "uk_50k.txt"),
    "ro": _freq_url("ro", "ro_50k.txt"),
    "ar": _freq_url("ar", "ar_50k.txt"),
    "ja": _freq_url("ja", "ja_full.txt"),
    "ko": _freq_url("ko", "ko_50k.txt"),
    "he": _freq_url("he", "he_50k.txt"),
    "hi": _freq_url("hi", "hi_full.txt"),
    "fa": _freq_url("fa", "fa_50k.txt"),
    "th": _freq_url("th", "th_50k.txt"),
    "bn": _freq_url("bn", "bn_50k.txt"),
    "vi": _freq_url("vi", "vi_50k.txt"),
    "zh_cn": _freq_url("zh_cn", "zh_cn_50k.txt"),
    "cs": _freq_url("cs", "cs_50k.txt"),
    "da": _freq_url("da", "da_50k.txt"),
    "el": _freq_url("el", "el_50k.txt"),
    "fi": _freq_url("fi", "fi_50k.txt"),
    "hu": _freq_url("hu", "hu_50k.txt"),
    "no": _freq_url("no", "no_50k.txt"),
    "ms": _freq_url("ms", "ms_50k.txt"),
    "ur": _freq_url("ur", "ur_50k.txt"),
    "sw": _freq_url("sw", "sw_50k.txt"),
    "tl": _freq_url("tl", "tl_50k.txt"),
    "ca": _freq_url("ca", "ca_50k.txt"),
    "hr": _freq_url("hr", "hr_50k.txt"),
    "sk": _freq_url("sk", "sk_50k.txt"),
    "bg": _freq_url("bg", "bg_50k.txt"),
    "sr": _freq_url("sr", "sr_50k.txt"),
    "lt": _freq_url("lt", "lt_50k.txt"),
    "lv": _freq_url("lv", "lv_50k.txt"),
    "et": _freq_url("et", "et_50k.txt"),
    "sl": _freq_url("sl", "sl_50k.txt"),
    "af": _freq_url("af", "af_50k.txt"),
    "sq": _freq_url("sq", "sq_50k.txt"),
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
    "passwords_darkweb10k.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/darkweb2017_top-10000.txt"
    ),
    "passwords_ncsc100k.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt"
    ),
    "passwords_pwdb100k.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/Pwdb_top-100000.txt"
    ),
    "passwords_pwdb1m.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/Pwdb_top-1000000.txt"
    ),
    "passwords_probable12k.txt": (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/probable-v2_top-12000.txt"
    ),
    "quran_en_pickthall.txt": "https://tanzil.net/trans/en.pickthall",
    "quran_en_yusufali.txt": "https://tanzil.net/trans/en.yusufali",
    "quran_en_sahih.txt": "https://tanzil.net/trans/en.sahih",
    "quran_en_arberry.txt": "https://tanzil.net/trans/en.arberry",
    "quran_fr_hamidullah.txt": "https://tanzil.net/trans/fr.hamidullah",
    "quran_es_garcia.txt": "https://tanzil.net/trans/es.garcia",
    "quran_ru_kuliev.txt": "https://tanzil.net/trans/ru.kuliev",
    "quran_de_aburida.txt": "https://tanzil.net/trans/de.aburida",
    "quran_tr_diyanet.txt": "https://tanzil.net/trans/tr.diyanet",
    "quran_zh_jian.txt": "https://tanzil.net/trans/zh.jian",
    "quran_fa_fooladvand.txt": "https://tanzil.net/trans/fa.fooladvand",
    "quran_id_indonesian.txt": "https://tanzil.net/trans/id.indonesian",
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
    "frankenstein.txt": "https://www.gutenberg.org/files/84/84-0.txt",
    "pride.txt": "https://www.gutenberg.org/files/1342/1342-0.txt",
    "sherlock.txt": "https://www.gutenberg.org/files/1661/1661-0.txt",
    "dracula.txt": "https://www.gutenberg.org/files/345/345-0.txt",
    "oz.txt": "https://www.gutenberg.org/files/55/55-0.txt",
    "christmascarol.txt": "https://www.gutenberg.org/files/46/46-0.txt",
    "twocities.txt": "https://www.gutenberg.org/files/98/98-0.txt",
    "huckfinn.txt": "https://www.gutenberg.org/files/76/76-0.txt",
    "doriangray.txt": "https://www.gutenberg.org/files/174/174-0.txt",
    "janeeyre.txt": "https://www.gutenberg.org/files/1260/1260-0.txt",
    "treasure.txt": "https://www.gutenberg.org/files/120/120-0.txt",
    "waroftheworlds.txt": "https://www.gutenberg.org/files/36/36-0.txt",
    "jekyll.txt": "https://www.gutenberg.org/files/43/43-0.txt",
    "prince.txt": "https://www.gutenberg.org/files/1232/1232-0.txt",
    "peterpan.txt": "https://www.gutenberg.org/files/16/16-0.txt",
    "pinocchio.txt": "https://www.gutenberg.org/files/244/244-0.txt",
    "federalist.txt": "https://www.gutenberg.org/files/1404/1404-0.txt",
    "declaration.txt": "https://www.gutenberg.org/files/1/1-0.txt",
    "paradiselost.txt": "https://www.gutenberg.org/files/26/26-0.txt",
    "mormon.txt": "https://www.gutenberg.org/files/17/17-0.txt",
    "gita.txt": "https://www.gutenberg.org/files/2388/2388.txt",
    "dhammapada.txt": "https://www.gutenberg.org/files/2017/2017-0.txt",
    "eff_large.txt": "https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt",
    "world_cities.csv": (
        "https://raw.githubusercontent.com/datasets/world-cities/master/data/world-cities.csv"
    ),
}

BIBLE_JSON = {
    f"bible_{abbrev}.json": (
        f"https://raw.githubusercontent.com/thiagobodruk/bible/master/json/{abbrev}.json"
    )
    for abbrev in (
        "ar_svd",
        "de_schlachter",
        "el_greek",
        "eo_esperanto",
        "es_rvr",
        "fi_finnish",
        "fi_pr",
        "fr_apee",
        "ko_ko",
        "pt_aa",
        "pt_acf",
        "pt_nvi",
        "ro_cornilescu",
        "ru_synodal",
        "vi_vietnamese",
        "zh_cuv",
        "zh_ncv",
    )
}

BIP39_FILES = {
    "bip39_spanish.txt": "spanish.txt",
    "bip39_french.txt": "french.txt",
    "bip39_italian.txt": "italian.txt",
    "bip39_japanese.txt": "japanese.txt",
    "bip39_korean.txt": "korean.txt",
    "bip39_czech.txt": "czech.txt",
    "bip39_portuguese.txt": "portuguese.txt",
    "bip39_chinese_simplified.txt": "chinese_simplified.txt",
    "bip39_chinese_traditional.txt": "chinese_traditional.txt",
}

DOWNLOADS.update(BIBLE_JSON)
DOWNLOADS.update(
    {
        name: (
            "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/" + filename
        )
        for name, filename in BIP39_FILES.items()
    }
)

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
    "a purely peer-to-peer version of electronic cash would allow online payments",
    "digital signatures provide part of the solution",
    "we propose a solution to the double-spending problem using a peer-to-peer network",
    "the network timestamps transactions by hashing them into an ongoing chain of hash-based proof-of-work",
    "the longest chain not only serves as proof of the sequence of events witnessed",
    "nodes can leave and rejoin the network at will",
    "new transactions are broadcast to all nodes",
    "each node collects new transactions into a block",
    "nodes express their acceptance of the block by working on creating the next block in the chain",
    "incentive can help encourage nodes to stay honest",
    "simplified payment verification",
    "hash-based proof-of-work",
    "peer-to-peer electronic cash system",
    "without going through a financial institution",
    "genesis block",
    "block 0",
    "block zero",
    "the times 03/jan/2009 chancellor on brink of second bailout for banks",
    "i am not satoshi",
    "we are all satoshi",
    "not your bitcoin not your keys",
    "hodl",
    "hodling",
    "to the moon",
    "laser eyes",
    "fix the money fix the world",
    "sound money",
    "hard money",
    "can't print more",
    "cant print more",
    "one bitcoin",
    "21 million bitcoin",
    "satoshi nakamoto",
    "craig wright is not satoshi",
    "len sassaman",
    "adam back",
    "wei dai",
    "b-money",
    "bit gold",
    "hashcash",
    "tim may",
    "crypto anarchist manifesto",
    "cypherpunks write code",
    "a cypherpunk's manifesto",
    "privacy is necessary for an open society in the electronic age",
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


def load_cities(path: Path, limit: int = 8000) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            city = (row.get("name") or row.get("Name") or "").strip()
            country = (row.get("country") or row.get("Country") or "").strip()
            key = city.lower()
            if len(city) < 3 or key in seen:
                continue
            seen.add(key)
            rows.append((city, country))
            if len(rows) >= limit:
                break
    return rows


def load_eff_words(path: Path) -> list[str]:
    words: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.strip().split()
            if not parts:
                continue
            word = parts[-1]
            if word.isalpha() and 3 <= len(word) <= 40:
                words.append(word.lower())
    return words


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
            if self.written % 1_000_000 == 0:
                self.handle.flush()
                print(f"  wrote {self.written:,} new / skipped {self.skipped:,}", file=sys.stderr)


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
    compact = "".join(words)
    if compact and len(compact) >= 6 and compact != strip_punctuation(text):
        emitter.emit(source, compact, nopunct=False)


def generate(emitter: Emitter) -> None:
    print("Generating new seed candidates...", file=sys.stderr)

    for phrase in EXTRA_PHRASES:
        emitter.emit("extra", phrase)

    for year in range(1950, 2027):
        emitter.emit("year", str(year), nopunct=False)
        emitter.emit("year", f"bitcoin {year}")
        emitter.emit("year", f"password{year}", nopunct=False)

    password_files = (
        "passwords_10k.txt",
        "passwords_100k.txt",
        "passwords_1m.txt",
        "passwords_darkweb.txt",
        "passwords_darkweb10k.txt",
        "passwords_rockyou75.txt",
        "passwords_ncsc100k.txt",
        "passwords_pwdb100k.txt",
        "passwords_pwdb1m.txt",
        "passwords_probable12k.txt",
    )
    for name in password_files:
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
        ("quran_en_sahih.txt", "quran-en-sahih"),
        ("quran_en_arberry.txt", "quran-en-arberry"),
        ("quran_fr_hamidullah.txt", "quran-fr"),
        ("quran_es_garcia.txt", "quran-es"),
        ("quran_ru_kuliev.txt", "quran-ru"),
        ("quran_de_aburida.txt", "quran-de"),
        ("quran_tr_diyanet.txt", "quran-tr"),
        ("quran_zh_jian.txt", "quran-zh"),
        ("quran_fa_fooladvand.txt", "quran-fa"),
        ("quran_id_indonesian.txt", "quran-id"),
    ):
        path = CORPORA / name
        if not path.exists():
            continue
        ayahs = load_tanzil_ayahs(path)
        print(f"  {source} {len(ayahs):,} ayahs...", file=sys.stderr)
        for surah, ayah, text in ayahs:
            emit_scripture_verse(emitter, source, "Quran", surah, ayah, text)
            emitter.emit(source, f"{surah}:{ayah} {text}")

    for path in sorted(CORPORA.glob("bible_*.json")):
        source = f"bible-{path.stem.replace('bible_', '')}"
        verses = load_bbe_verses(path)
        print(f"  {source} {len(verses):,} verses...", file=sys.stderr)
        for book, chapter, verse, text in verses:
            emit_scripture_verse(emitter, source, book, chapter, verse, text)

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

    cities_path = CORPORA / "world_cities.csv"
    if cities_path.exists():
        cities = load_cities(cities_path)
        print(f"  cities {len(cities):,}...", file=sys.stderr)
        for city, country in cities:
            emitter.emit("geo", city)
            emitter.emit("geo", f"bitcoin {city}")
            if country:
                emitter.emit("geo", f"{city} {country}")

    for path in sorted(CORPORA.glob("bip39_*.txt")):
        words = load_password_lines(path)
        source = f"bip39:{path.stem.replace('bip39_', '')}"
        print(f"  {source} {len(words)} words...", file=sys.stderr)
        for word in words:
            emitter.emit(source, word, nopunct=False)
        phrase_top = {2: 150, 3: 30, 4: 15} if path.name != "bip39_en.txt" else {2: 200, 3: 50, 4: 20}
        for phrase in iter_dictionary_phrases(
            words,
            phrase_lengths=(2, 3, 4),
            top_n_by_length=phrase_top,
        ):
            emitter.emit(f"{source}:phrase", phrase, nopunct=False)

    eff_path = CORPORA / "eff_large.txt"
    if eff_path.exists():
        words = load_eff_words(eff_path)
        print(f"  EFF diceware {len(words)} words...", file=sys.stderr)
        for word in words:
            emitter.emit("eff", word, nopunct=False)
        for phrase in iter_dictionary_phrases(
            words,
            phrase_lengths=(2, 3, 4),
            top_n_by_length={2: 200, 3: 40, 4: 18},
        ):
            emitter.emit("eff:phrase", phrase, nopunct=False)

    book_names = (
        "alice.txt",
        "shakespeare.txt",
        "artofwar.txt",
        "taoteching.txt",
        "constitution.txt",
        "gettysburg.txt",
        "moby.txt",
        "frankenstein.txt",
        "pride.txt",
        "sherlock.txt",
        "dracula.txt",
        "oz.txt",
        "christmascarol.txt",
        "twocities.txt",
        "huckfinn.txt",
        "doriangray.txt",
        "janeeyre.txt",
        "treasure.txt",
        "waroftheworlds.txt",
        "jekyll.txt",
        "prince.txt",
        "peterpan.txt",
        "pinocchio.txt",
        "federalist.txt",
        "declaration.txt",
        "paradiselost.txt",
        "mormon.txt",
        "gita.txt",
        "dhammapada.txt",
    )
    for name in book_names:
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
