#!/usr/bin/env python3
"""Build a high-quality brainwallet candidate list from public sources.

Downloads (and caches) common-password and dictionary lists, mixes in the
curated seeds under data/seeds.txt, then emits unique printable-ASCII
phrases with *light* mutations. Full 2^n case explosion is intentionally
not used — that path is case_variants.py and explodes too fast for a
usable list.

Sources are public wordlists, not leaked full dumps. Output is for the
existing brainflayer -i path against a filter you already hold.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Iterator, Sequence

MIN_LEN = 1
MAX_LEN = 64
USER_AGENT = "brainflayer-wordlist/1.0 (+https://github.com/AppleLamps/brainflayer)"

SOURCES = (
    (
        "xato-net-10-million-passwords-100000.txt",
        (
            "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/xato-net-10-million-passwords-100000.txt",
        ),
    ),
    (
        "10k-most-common.txt",
        (
            "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10k-most-common.txt",
        ),
    ),
    (
        "google-10000-english.txt",
        (
            "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english.txt",
        ),
    ),
    (
        "bip39-english.txt",
        (
            "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt",
        ),
    ),
    (
        "eff_large_wordlist.txt",
        (
            "https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt",
        ),
    ),
    (
        "zxcvbn-passwords.txt",
        (
            "https://raw.githubusercontent.com/dropbox/zxcvbn/master/data/passwords.txt",
        ),
    ),
    (
        "zxcvbn-english.txt",
        (
            "https://raw.githubusercontent.com/dropbox/zxcvbn/master/data/english_wikipedia.txt",
        ),
    ),
)

STOPWORDS = frozenset(
    """
    a an the of and or to in on for is it as at by be we he she they you i
    from with that this these those not no nor but if then so than too very
    was were been being are am do did does doing have has had having will
    would could should can may might must shall about into over after before
    between through during without within until while also just only own same
    other some any each every both few more most other such own s t don now
    here there when where why how all
    """.split()
)

PAIR_STOP = STOPWORDS | frozenset(
    """
    page search site web www http https html php asp com net org edu gov
    click view online email contact copyright policy please available
    support message info rights privacy terms website us our your their
    his her them who what which get like find see use out buy add post
    services service products product software data system number date
    price list jan feb mar apr jun jul aug sep oct nov dec
    mon tue wed thu fri sat sun
    information news business help first next used last top back
    """.split()
)

SUFFIXES = (
    "1",
    "12",
    "123",
    "1234",
    "12345",
    "123456",
    "!",
    "!!",
    "!1",
    "1!",
    "@",
    "#",
    "$",
    "?",
    ".",
    "00",
    "01",
    "69",
    "420",
    "666",
    "777",
    "1337",
    "xyz",
    "abc",
    "qwer",
)

YEARS_BTC = tuple(str(year) for year in range(2009, 2018))
YEARS_LIFE = tuple(str(year) for year in range(1965, 2017))
PINS = ("0000", "1111", "1234", "4321", "2580", "0852", "1212", "1004", "2000", "2001")

LEET_MAP = (
    ("a", "@"),
    ("e", "3"),
    ("i", "1"),
    ("o", "0"),
    ("s", "$"),
    ("t", "7"),
)

FIRST_NAMES = (
    "james", "john", "robert", "michael", "william", "david", "richard",
    "joseph", "thomas", "charles", "christopher", "daniel", "matthew",
    "anthony", "mark", "donald", "steven", "paul", "andrew", "joshua",
    "kenneth", "kevin", "brian", "george", "timothy", "ronald", "edward",
    "jason", "jeffrey", "ryan", "jacob", "gary", "nicholas", "eric",
    "jonathan", "stephen", "larry", "justin", "scott", "brandon", "benjamin",
    "samuel", "raymond", "gregory", "frank", "alexander", "patrick", "jack",
    "dennis", "jerry", "tyler", "aaron", "jose", "adam", "henry", "nathan",
    "douglas", "zachary", "peter", "kyle", "noah", "ethan", "jeremy",
    "walter", "christian", "keith", "roger", "terry", "austin", "sean",
    "mary", "patricia", "jennifer", "linda", "elizabeth", "barbara", "susan",
    "jessica", "sarah", "karen", "nancy", "lisa", "betty", "margaret",
    "sandra", "ashley", "kimberly", "emily", "donna", "michelle", "dorothy",
    "carol", "amanda", "melissa", "deborah", "stephanie", "rebecca", "sharon",
    "laura", "cynthia", "kathleen", "amy", "angela", "shirley", "anna",
    "brenda", "pamela", "emma", "nicole", "helen", "samantha", "katherine",
    "christine", "debra", "rachel", "carolyn", "janet", "catherine", "maria",
    "heather", "diane", "virginia", "julie", "joyce", "victoria", "olivia",
    "satoshi", "nakamoto", "dorian", "hal", "finney", "nick", "szabo",
    "vitalik", "andreas", "gavin", "roger", "charlie", "max", "pierre",
)

LAST_NAMES = (
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller",
    "davis", "rodriguez", "martinez", "hernandez", "lopez", "gonzalez",
    "wilson", "anderson", "thomas", "taylor", "moore", "jackson", "martin",
    "lee", "perez", "thompson", "white", "harris", "sanchez", "clark",
    "ramirez", "lewis", "robinson", "walker", "young", "allen", "king",
    "wright", "scott", "torres", "nguyen", "hill", "flores", "green",
    "adams", "nelson", "baker", "hall", "rivera", "campbell", "mitchell",
    "carter", "roberts", "nakamoto", "finney", "szabo",
)

NOUNS = (
    "bitcoin", "money", "gold", "love", "life", "wife", "husband", "kids",
    "family", "dog", "cat", "god", "jesus", "satoshi", "password", "secret",
    "treasure", "key", "keys", "private", "moon", "sun", "star", "dragon",
    "master", "shadow", "hunter", "princess", "angel", "baby", "honey",
    "cash", "coin", "coins", "btc", "wallet", "bank", "home", "house",
    "freedom", "peace", "hope", "dream", "future", "past", "soul", "heart",
    "mind", "power", "glory", "honor", "truth", "faith", "grace", "light",
    "dark", "death", "war", "fire", "water", "earth", "wind", "sky", "sea",
    "king", "queen", "prince", "lord", "lady", "baby", "mama", "papa",
    "daddy", "mommy", "son", "daughter", "brother", "sister", "friend",
    "lover", "baby", "sunshine", "rainbow", "diamond", "pearl", "ruby",
    "crown", "sword", "shield", "castle", "garden", "river", "mountain",
    "forest", "ocean", "island", "paradise", "heaven", "hell", "eden",
    "zion", "babel", "omega", "alpha", "matrix", "oracle", "phoenix",
    "tiger", "lion", "eagle", "wolf", "bear", "snake", "spider", "hawk",
    "falcon", "raven", "crow", "fox", "horse", "unicorn", "wizard", "witch",
    "ninja", "samurai", "pirate", "ninja", "cowboy", "outlaw", "bandit",
    "fortune", "destiny", "karma", "luck", "magic", "spell", "charm",
    "cookie", "pizza", "coffee", "beer", "wine", "whiskey", "vodka",
    "satan", "lucifer", "devil", "demon", "angel", "saint", "pope",
    "america", "england", "russia", "china", "japan", "germany", "france",
    "canada", "mexico", "brazil", "india", "israel", "rome", "paris",
    "london", "tokyo", "newyork", "chicago", "boston", "texas", "california",
    "florida", "vegas", "miami", "seattle", "austin", "denver", "portland",
)

TEMPLATES = (
    "i love {n}",
    "i love my {n}",
    "my {n}",
    "my {n} 123",
    "{n} is money",
    "secret {n}",
    "hidden {n}",
    "the {n}",
    "{n} wallet",
    "my {n} wallet",
    "{n} bitcoin",
    "bitcoin {n}",
    "hello {n}",
    "dear {n}",
    "{n} 123",
    "{n} password",
    "password {n}",
    "i am {n}",
    "we are {n}",
    "god {n}",
    "love {n}",
    "{n} love",
    "super {n}",
    "mega {n}",
    "dark {n}",
    "holy {n}",
    "sacred {n}",
    "eternal {n}",
    "forever {n}",
    "{n} forever",
    "please {n}",
    "remember {n}",
    "forget {n}",
    "save {n}",
    "my secret {n}",
    "{n} is the key",
    "the key is {n}",
    "{n} nakamoto",
    "satoshi {n}",
)

JOINERS = (" ", "", "-", "_", ".")


def acceptable(candidate: str) -> bool:
    if not candidate or len(candidate) < MIN_LEN or len(candidate) > MAX_LEN:
        return False
    for char in candidate:
        if not 32 <= ord(char) <= 126:
            return False
    return not candidate.isspace()


def light_cases(candidate: str) -> Iterator[str]:
    yield candidate
    lowered = candidate.lower()
    if lowered != candidate:
        yield lowered
    if candidate.isalpha() or " " in candidate or "-" in candidate:
        titled = candidate.title()
        if titled != candidate:
            yield titled
        capped = candidate[:1].upper() + candidate[1:]
        if capped != candidate:
            yield capped
        if len(candidate) <= 32:
            uppered = candidate.upper()
            if uppered != candidate:
                yield uppered


def separator_variants(candidate: str) -> Iterator[str]:
    yield candidate
    if " " in candidate:
        yield candidate.replace(" ", "")
        yield candidate.replace(" ", "-")
        yield candidate.replace(" ", "_")
        yield " ".join(candidate.split())
    if "-" in candidate and " " not in candidate:
        yield candidate.replace("-", " ")
        yield candidate.replace("-", "")
        yield candidate.replace("-", "_")


def leet_variants(candidate: str) -> Iterator[str]:
    if not (3 <= len(candidate) <= 12):
        return
    lowered = candidate.lower()
    present = [(src, dst) for src, dst in LEET_MAP if src in lowered]
    for src, dst in present:
        yield lowered.replace(src, dst)
    if len(present) >= 2:
        all_leet = lowered
        for src, dst in present:
            all_leet = all_leet.replace(src, dst)
        yield all_leet
        for i, (src_a, dst_a) in enumerate(present):
            for src_b, dst_b in present[i + 1 :]:
                yield lowered.replace(src_a, dst_a).replace(src_b, dst_b)


def mutate(candidate: str, *, heavy: bool = False) -> Iterator[str]:
    seen: set[str] = set()
    for variant in separator_variants(candidate):
        for cased in light_cases(variant):
            if cased not in seen and acceptable(cased):
                seen.add(cased)
                yield cased

    base = candidate.strip()
    if not acceptable(base) or " " in base or not (3 <= len(base) <= 16):
        return

    extras = SUFFIXES if heavy else SUFFIXES[:12]
    years = YEARS_BTC + (("69", "88", "99", "00", "007") if heavy else ())
    for suffix in extras + years:
        item = base + suffix
        if item not in seen and acceptable(item):
            seen.add(item)
            yield item
        titled = base[:1].upper() + base[1:] + suffix
        if titled not in seen and acceptable(titled):
            seen.add(titled)
            yield titled

    if heavy and base.isalpha() and 4 <= len(base) <= 8:
        reversed_base = base[::-1]
        if reversed_base not in seen and acceptable(reversed_base):
            seen.add(reversed_base)
            yield reversed_base
        for leet in leet_variants(base):
            if leet not in seen and acceptable(leet):
                seen.add(leet)
                yield leet


def parse_source_lines(text: str, *, eff: bool = False) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if eff:
            if "\t" in line:
                line = line.split("\t", 1)[1].strip()
            else:
                parts = line.split()
                line = parts[-1] if parts else ""
        else:
            parts = line.split()
            if len(parts) == 2 and parts[1].isdigit():
                line = parts[0]
        if acceptable(line):
            out.append(line)
    return out


def parse_hunspell(path: Path) -> list[str]:
    stems: list[str] = []
    with path.open(encoding="utf-8", errors="ignore") as handle:
        next(handle, None)
        for raw in handle:
            stem = raw.split("/", 1)[0].strip()
            if 2 <= len(stem) <= 20 and acceptable(stem):
                stems.append(stem)
                lowered = stem.lower()
                if lowered != stem and acceptable(lowered):
                    stems.append(lowered)
    return stems


def download(url: str, dest: Path, timeout: int = 60) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, 5):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if getattr(response, "status", 200) >= 400:
                    raise urllib.error.HTTPError(url, response.status, "download", response.headers, None)
                data = response.read()
            if not data:
                raise RuntimeError(f"empty download from {url}")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            last_error = exc
            if attempt < 4:
                continue
    raise RuntimeError(f"failed to download {url}: {last_error}") from last_error


def download_first(urls: Sequence[str], dest: Path) -> None:
    errors: list[str] = []
    for url in urls:
        try:
            download(url, dest)
            return
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors))


class Emitter:
    def __init__(self, handle, limit: int | None) -> None:
        self.handle = handle
        self.limit = limit
        self.seen: set[str] = set()
        self.count = 0
        self.skipped = 0

    def add(self, candidate: str) -> bool:
        if self.limit is not None and self.count >= self.limit:
            return False
        if not acceptable(candidate) or candidate in self.seen:
            self.skipped += 1
            return True
        self.seen.add(candidate)
        self.handle.write(candidate)
        self.handle.write("\n")
        self.count += 1
        return self.limit is None or self.count < self.limit

    def add_many(self, candidates: Iterable[str]) -> bool:
        for candidate in candidates:
            if not self.add(candidate):
                return False
        return True


def content_words(words: Sequence[str], limit: int, *, stops: frozenset[str] | None = None, min_len: int = 3) -> list[str]:
    blocked = STOPWORDS if stops is None else stops
    out: list[str] = []
    seen: set[str] = set()
    for word in words:
        item = word.lower()
        if item in blocked or not item.isalpha() or not (min_len <= len(item) <= 12):
            continue
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def pair_phrases(words: Sequence[str], count: int, joiners: Sequence[str]) -> Iterator[str]:
    selected = list(words[:count])
    for left in selected:
        for right in selected:
            if left == right:
                continue
            for joiner in joiners:
                yield f"{left}{joiner}{right}"


def triple_phrases(words: Sequence[str], count: int) -> Iterator[str]:
    selected = list(words[:count])
    for first in selected:
        for second in selected:
            if second == first:
                continue
            for third in selected:
                if third == first or third == second:
                    continue
                yield f"{first} {second} {third}"


def load_cached(path: Path, urls: Sequence[str], offline: bool) -> str:
    if path.is_file() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8", errors="ignore")
    if offline:
        raise FileNotFoundError(f"missing cached source {path} (offline mode)")
    download_first(urls, path)
    return path.read_text(encoding="utf-8", errors="ignore")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_wordlist(
    *,
    output: Path,
    cache_dir: Path,
    seeds_path: Path,
    hunspell_path: Path | None,
    limit: int | None,
    offline: bool,
    with_pairs: bool,
    with_mutations: bool,
) -> Emitter:
    output.parent.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    sources: dict[str, list[str]] = {}
    for filename, urls in SOURCES:
        try:
            text = load_cached(cache_dir / filename, urls, offline)
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"[!] skip {filename}: {exc}", file=sys.stderr)
            sources[filename] = []
            continue
        sources[filename] = parse_source_lines(text, eff=filename.startswith("eff_"))
        print(f"[*] {filename}: {len(sources[filename]):,} lines", file=sys.stderr)

    hunspell: list[str] = []
    if hunspell_path is not None and hunspell_path.is_file():
        hunspell = parse_hunspell(hunspell_path)
        print(f"[*] hunspell {hunspell_path}: {len(hunspell):,} stems", file=sys.stderr)
    elif hunspell_path is not None:
        print(f"[!] hunspell not found at {hunspell_path}, skipping", file=sys.stderr)

    seeds: list[str] = []
    if seeds_path.is_file():
        seeds = parse_source_lines(seeds_path.read_text(encoding="utf-8", errors="ignore"))
        print(f"[*] seeds {seeds_path}: {len(seeds):,} phrases", file=sys.stderr)

    passwords = list(
        dict.fromkeys(
            [
                *sources.get("xato-net-10-million-passwords-100000.txt", []),
                *sources.get("10k-most-common.txt", []),
                *sources.get("zxcvbn-passwords.txt", []),
            ]
        )
    )
    google = list(
        dict.fromkeys(
            [
                *sources.get("google-10000-english.txt", []),
                *sources.get("zxcvbn-english.txt", []),
            ]
        )
    )
    bip39 = sources.get("bip39-english.txt", [])
    eff = sources.get("eff_large_wordlist.txt", [])
    common10k = sources.get("10k-most-common.txt", [])

    with output.open("w", encoding="ascii", errors="ignore", newline="\n") as handle:
        emitter = Emitter(handle, limit)

        print("[*] phase 1: curated seeds + templates", file=sys.stderr)
        before = emitter.count
        for seed in seeds:
            if not emitter.add_many(mutate(seed, heavy=True)):
                return emitter
        for noun in NOUNS:
            for template in TEMPLATES:
                if not emitter.add_many(mutate(template.format(n=noun), heavy=False)):
                    return emitter
        print(f"    {emitter.count - before:,} new (total {emitter.count:,})", file=sys.stderr)

        print("[*] phase 2: common passwords + names", file=sys.stderr)
        before = emitter.count
        if not emitter.add_many(passwords):
            return emitter
        if not emitter.add_many(common10k):
            return emitter
        for name in FIRST_NAMES + LAST_NAMES:
            if not emitter.add(name):
                return emitter
            if not emitter.add(name.capitalize()):
                return emitter
            for year in YEARS_LIFE:
                if not emitter.add(name + year):
                    return emitter
                if not emitter.add(name.capitalize() + year):
                    return emitter
            for pin in PINS + SUFFIXES[:8]:
                if not emitter.add(name + pin):
                    return emitter
        for name in FIRST_NAMES[:80]:
            for noun in NOUNS[:80]:
                if not emitter.add(f"{name} {noun}"):
                    return emitter
                if not emitter.add(f"{name.capitalize()} {noun}"):
                    return emitter
                if not emitter.add(f"{name}{noun}"):
                    return emitter
        if with_mutations:
            for password in passwords[:25000]:
                if not emitter.add_many(mutate(password, heavy=len(password) <= 10)):
                    return emitter
        print(f"    {emitter.count - before:,} new (total {emitter.count:,})", file=sys.stderr)

        print("[*] phase 3: dictionaries as-is", file=sys.stderr)
        before = emitter.count
        if not emitter.add_many(google):
            return emitter
        if not emitter.add_many(bip39):
            return emitter
        if not emitter.add_many(eff):
            return emitter
        if not emitter.add_many(hunspell):
            return emitter
        print(f"    {emitter.count - before:,} new (total {emitter.count:,})", file=sys.stderr)

        print("[*] phase 4: light dictionary mutations", file=sys.stderr)
        before = emitter.count
        if with_mutations:
            for word in google[:12000]:
                if not emitter.add_many(mutate(word, heavy=len(word) <= 8)):
                    return emitter
            for word in bip39:
                if not emitter.add_many(mutate(word, heavy=False)):
                    return emitter
            common = {word.lower() for word in google[:30000]}
            common.update(word.lower() for word in passwords[:30000])
            for word in hunspell:
                if not (4 <= len(word) <= 8 and word.isalpha() and word.islower()):
                    continue
                if word not in common and len(word) > 6:
                    continue
                if not emitter.add_many((word + suffix for suffix in SUFFIXES[:8] + YEARS_BTC)):
                    return emitter
        print(f"    {emitter.count - before:,} new (total {emitter.count:,})", file=sys.stderr)

        if with_pairs:
            print("[*] phase 5: two- and three-word phrases", file=sys.stderr)
            before = emitter.count
            # Frequency-ordered English, minus web-chrome tokens; mix in BIP-39
            # words that people actually type as phrases.
            google_content = content_words(google, 500, stops=PAIR_STOP, min_len=4)
            bip_content = content_words(bip39, 256, stops=PAIR_STOP, min_len=4)
            pair_vocab = list(dict.fromkeys([*NOUNS, *google_content, *bip_content]))
            if not emitter.add_many(pair_phrases(pair_vocab, 320, (" ",))):
                return emitter
            if not emitter.add_many(pair_phrases(pair_vocab, 100, JOINERS)):
                return emitter
            if not emitter.add_many(pair_phrases(bip_content, 140, (" ", "-", ""))):
                return emitter
            if not emitter.add_many(triple_phrases(pair_vocab, 28)):
                return emitter
            print(f"    {emitter.count - before:,} new (total {emitter.count:,})", file=sys.stderr)

        return emitter


def self_test() -> None:
    assert acceptable("password")
    assert acceptable("correct horse battery staple")
    assert not acceptable("")
    assert not acceptable("a" * 65)
    assert not acceptable("bad\x00null")
    assert not acceptable("£nonascii")

    cases = set(light_cases("password"))
    assert "password" in cases
    assert "Password" in cases
    assert "PASSWORD" in cases

    seps = set(separator_variants("correct horse"))
    assert "correcthorse" in seps
    assert "correct-horse" in seps
    assert "correct_horse" in seps

    muts = set(mutate("password", heavy=True))
    for expected in (
        "password",
        "Password",
        "PASSWORD",
        "password1",
        "password123",
        "password!",
        "password2013",
        "p@ssword",
        "p@ssw0rd",
    ):
        assert expected in muts, expected

    phrase_muts = set(mutate("correct horse", heavy=True))
    assert "correct horse" in phrase_muts
    assert "correcthorse" in phrase_muts
    assert "correct-horse" in phrase_muts
    assert "correct horse123" not in phrase_muts
    assert "correct horse2013" not in phrase_muts

    parsed = parse_source_lines("# c\nfoo\nbar\n\n",)
    assert parsed == ["foo", "bar"]
    counted = parse_source_lines("password        20785\n123456\n")
    assert counted == ["password", "123456"]
    eff = parse_source_lines("11111\tabacus\n22222 zebra\n", eff=True)
    assert eff == ["abacus", "zebra"]

    words = content_words(["the", "Bitcoin", "money", "of", "sats"], 10)
    assert words == ["bitcoin", "money", "sats"]
    pair_words = content_words(
        ["click", "home", "bitcoin", "email", "dragon"],
        10,
        stops=PAIR_STOP,
        min_len=4,
    )
    assert pair_words == ["home", "bitcoin", "dragon"]

    pairs = list(pair_phrases(["love", "bitcoin"], 2, (" ", "-")))
    assert "love bitcoin" in pairs
    assert "love-bitcoin" in pairs
    assert "love love" not in pairs

    triples = list(triple_phrases(["correct", "horse", "battery"], 3))
    assert "correct horse battery" in triples
    assert "correct correct horse" not in triples

    print("self-test ok", file=sys.stderr)


def default_paths(root: Path) -> tuple[Path, Path, Path, Path]:
    return (
        root / "data" / "wordlist.txt",
        root / "data" / "wordlist-src",
        root / "data" / "seeds.txt",
        Path("/usr/share/hunspell/en_US.dic"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    root = repo_root()
    out_default, cache_default, seeds_default, hunspell_default = default_paths(root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-o", "--output", type=Path, default=out_default)
    parser.add_argument("--cache-dir", type=Path, default=cache_default)
    parser.add_argument("--seeds", type=Path, default=seeds_default)
    parser.add_argument("--hunspell", type=Path, default=hunspell_default)
    parser.add_argument("--max", type=int, default=0, help="stop after N unique phrases (0 = no cap)")
    parser.add_argument("--offline", action="store_true", help="do not download; use cache only")
    parser.add_argument("--no-pairs", action="store_true")
    parser.add_argument("--no-mutations", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        self_test()
        return 0
    if args.max < 0:
        parser.error("--max must be non-negative")

    limit = args.max if args.max else None
    hunspell = None if str(args.hunspell) in {"", "none"} else args.hunspell
    emitter = build_wordlist(
        output=args.output,
        cache_dir=args.cache_dir,
        seeds_path=args.seeds,
        hunspell_path=hunspell,
        limit=limit,
        offline=args.offline,
        with_pairs=not args.no_pairs,
        with_mutations=not args.no_mutations,
    )
    print(
        f"[+] wrote {emitter.count:,} unique phrases to {args.output} "
        f"(skipped {emitter.skipped:,} empty/duplicate/invalid)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
