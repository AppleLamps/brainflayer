#!/usr/bin/env python3
"""Stream high-quality multi-billion brainwallet phrases to stdout.

This is the opposite of the earlier cartesian dumps (top-500 function words,
ALL CAPS, reversed). Those spaces are already well-trodden. These modes use
*memorable content words* plus *English syntax*, or mnemonic systems that
early bitcoiners actually knew, and they stream so we never write a 100 GB file.

Modes (see --list):
  title   "the {adj} {noun} of the {noun}"   book-title grammar
  of      "{adj} {noun} of {noun}"
  paint   "{adj} {adj} {noun}"               xkcd-like, adjectives constrained
  pgp4    PGP even-odd-even-odd 4-word
  bip39_3 full BIP39 English 3-word (not the tiny top-N we already tested)
  name    "{name}'s {adj} {noun}"
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORPORA = ROOT / "data" / "corpora"
QUALITY = CORPORA / "quality"
UA = "brainflayer-seedgen/1.0"

MOBY_URL = "https://www.gutenberg.org/files/3203/files/mobypos.txt"
EFF_URL = "https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt"
BIP39_URL = "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt"
PGP_URL = (
    "https://raw.githubusercontent.com/magic-wormhole/magic-wormhole/"
    "master/src/wormhole/_wordlist.py"
)
NAMES_URL = (
    "https://raw.githubusercontent.com/dominictarr/random-name/master/first-names.txt"
)

WORD_RE = re.compile(r"^[a-z]{3,12}$")
PGP_PAIR_RE = re.compile(
    r"'[0-9A-Fa-f]{2}':\s*\['([^']+)',\s*'([^']+)'\]"
)


def download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def write_lines(path: Path, words: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(word + "\n" for word in words), encoding="utf-8")


def read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fetch_file(name: str, url: str) -> Path:
    dest = QUALITY / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 100:
        return dest
    dest.write_bytes(download(url))
    return dest


def parse_moby_exclusive(raw: str) -> tuple[set[str], set[str]]:
    nouns: set[str] = set()
    adjs: set[str] = set()
    for line in raw.splitlines():
        if "\\" not in line:
            continue
        word, pos = line.split("\\", 1)
        word = word.strip().lower()
        if not WORD_RE.fullmatch(word):
            continue
        letters = {char for char in pos if char.isalpha()}
        if letters == {"N"}:
            nouns.add(word)
        elif letters == {"A"}:
            adjs.add(word)
    return nouns, adjs


def parse_eff(raw: str) -> list[str]:
    words: list[str] = []
    for line in raw.splitlines():
        parts = line.split()
        if not parts:
            continue
        word = parts[-1].lower()
        if WORD_RE.fullmatch(word):
            words.append(word)
    return words


def parse_pgp(raw: str) -> tuple[list[str], list[str]]:
    even: list[str] = []
    odd: list[str] = []
    for match in PGP_PAIR_RE.finditer(raw):
        even.append(match.group(1).lower())
        odd.append(match.group(2).lower())
    if len(even) != 256 or len(odd) != 256:
        raise SystemExit(f"PGP wordlist parse failed: even={len(even)} odd={len(odd)}")
    return even, odd


def parse_names(raw: str, limit: int = 1500) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        name = line.strip().strip('"').lower()
        if not WORD_RE.fullmatch(name) or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= limit:
            break
    return names


def build_pos_lists() -> tuple[list[str], list[str]]:
    adj_path = QUALITY / "adjs.txt"
    noun_path = QUALITY / "nouns.txt"
    if adj_path.exists() and noun_path.exists():
        return read_lines(adj_path), read_lines(noun_path)

    print("Building adjective/noun lists from EFF ∩ Moby exclusive POS ...", file=sys.stderr)
    moby = fetch_file("mobypos.txt", MOBY_URL).read_text(encoding="latin-1", errors="replace")
    eff = parse_eff(fetch_file("eff_large.txt", EFF_URL).read_text(encoding="utf-8"))
    nouns, adjs = parse_moby_exclusive(moby)
    # Keep EFF order (diceware-style memorable words), not web-frequency junk.
    adj_list = [word for word in eff if word in adjs]
    noun_list = [word for word in eff if word in nouns]
    if len(adj_list) < 800 or len(noun_list) < 1500:
        raise SystemExit(
            f"POS lists too small: {len(adj_list)} adjs, {len(noun_list)} nouns"
        )
    write_lines(adj_path, adj_list)
    write_lines(noun_path, noun_list)
    print(f"  {len(adj_list):,} adjectives, {len(noun_list):,} nouns", file=sys.stderr)
    return adj_list, noun_list


def load_pgp() -> tuple[list[str], list[str]]:
    even_path = QUALITY / "pgp_even.txt"
    odd_path = QUALITY / "pgp_odd.txt"
    if even_path.exists() and odd_path.exists():
        return read_lines(even_path), read_lines(odd_path)
    even, odd = parse_pgp(fetch_file("pgp_wordlist.py", PGP_URL).read_text(encoding="utf-8"))
    write_lines(even_path, even)
    write_lines(odd_path, odd)
    return even, odd


def load_bip39() -> list[str]:
    cached = CORPORA / "bip39_en.txt"
    if cached.exists() and cached.stat().st_size > 100:
        words = read_lines(cached)
        if len(words) == 2048:
            return words
    path = fetch_file("bip39_en.txt", BIP39_URL)
    words = read_lines(path)
    if len(words) != 2048:
        raise SystemExit(f"BIP39 english should be 2048 words, got {len(words)}")
    return words


def load_names() -> list[str]:
    path = QUALITY / "first_names.txt"
    if path.exists():
        return read_lines(path)
    names = parse_names(fetch_file("first_names.txt", NAMES_URL).read_text(encoding="utf-8"))
    write_lines(path, names)
    return names


def iter_sharded_first(items: list[str], shard: int, shards: int) -> list[str]:
    if shards <= 1:
        return items
    return items[shard::shards]


def generate_title(adjs: list[str], nouns: list[str]) -> None:
    write = sys.stdout.write
    buf: list[str] = []
    push = buf.append
    for adj in adjs:
        head = "the " + adj + " "
        for noun1 in nouns:
            mid = head + noun1 + " of the "
            for noun2 in nouns:
                push(mid + noun2)
                if len(buf) >= 2048:
                    write("\n".join(buf))
                    write("\n")
                    buf.clear()
    if buf:
        write("\n".join(buf))
        write("\n")


def generate_of(adjs: list[str], nouns: list[str]) -> None:
    write = sys.stdout.write
    buf: list[str] = []
    push = buf.append
    for adj in adjs:
        for noun1 in nouns:
            mid = adj + " " + noun1 + " of "
            for noun2 in nouns:
                push(mid + noun2)
                if len(buf) >= 2048:
                    write("\n".join(buf))
                    write("\n")
                    buf.clear()
    if buf:
        write("\n".join(buf))
        write("\n")


def generate_paint(firsts: list[str], adjs: list[str], nouns: list[str]) -> None:
    write = sys.stdout.write
    buf: list[str] = []
    push = buf.append
    for adj1 in firsts:
        for adj2 in adjs:
            mid = adj1 + " " + adj2 + " "
            for noun in nouns:
                push(mid + noun)
                if len(buf) >= 2048:
                    write("\n".join(buf))
                    write("\n")
                    buf.clear()
    if buf:
        write("\n".join(buf))
        write("\n")


def generate_pgp4(even: list[str], odd: list[str], firsts: list[str]) -> None:
    write = sys.stdout.write
    buf: list[str] = []
    push = buf.append
    for w0 in firsts:
        for w1 in odd:
            left = w0 + " " + w1 + " "
            for w2 in even:
                mid = left + w2 + " "
                for w3 in odd:
                    push(mid + w3)
                    if len(buf) >= 2048:
                        write("\n".join(buf))
                        write("\n")
                        buf.clear()
    if buf:
        write("\n".join(buf))
        write("\n")


def generate_bip39_3(words: list[str], firsts: list[str]) -> None:
    write = sys.stdout.write
    buf: list[str] = []
    push = buf.append
    for w0 in firsts:
        for w1 in words:
            left = w0 + " " + w1 + " "
            for w2 in words:
                push(left + w2)
                if len(buf) >= 2048:
                    write("\n".join(buf))
                    write("\n")
                    buf.clear()
    if buf:
        write("\n".join(buf))
        write("\n")


def generate_name(names: list[str], adjs: list[str], nouns: list[str]) -> None:
    write = sys.stdout.write
    buf: list[str] = []
    push = buf.append
    for name in names:
        head = name + "'s "
        for adj in adjs:
            mid = head + adj + " "
            for noun in nouns:
                push(mid + noun)
                if len(buf) >= 2048:
                    write("\n".join(buf))
                    write("\n")
                    buf.clear()
    if buf:
        write("\n".join(buf))
        write("\n")


def sample_lines(mode: str, adjs: list[str], nouns: list[str], n: int = 8) -> list[str]:
    if mode == "title":
        return [f"the {adjs[0]} {nouns[0]} of the {nouns[i]}" for i in range(n)]
    if mode == "of":
        return [f"{adjs[0]} {nouns[0]} of {nouns[i]}" for i in range(n)]
    if mode == "paint":
        return [f"{adjs[0]} {adjs[1]} {nouns[i]}" for i in range(n)]
    if mode == "pgp4":
        even, odd = load_pgp()
        return [f"{even[0]} {odd[0]} {even[1]} {odd[i]}" for i in range(n)]
    if mode == "bip39_3":
        words = load_bip39()
        return [f"{words[0]} {words[1]} {words[i]}" for i in range(n)]
    if mode == "name":
        names = load_names()
        return [f"{names[0]}'s {adjs[0]} {nouns[i]}" for i in range(n)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        default="title",
        choices=("title", "of", "paint", "pgp4", "bip39_3", "name"),
        help="Phrase family to stream (default: title)",
    )
    parser.add_argument("--shard", default="0/1", help="i/N process split, shards the first word")
    parser.add_argument("--list", action="store_true", help="Print modes and counts, then exit")
    parser.add_argument("--sample", action="store_true", help="Print a few example phrases")
    args = parser.parse_args()

    shard_s, _, shards_s = args.shard.partition("/")
    shard = int(shard_s or 0)
    shards = int(shards_s or 1)
    if shards < 1 or shard < 0 or shard >= shards:
        raise SystemExit(f"invalid --shard {args.shard}")

    adjs, nouns = build_pos_lists()
    specs = {
        "title": (
            'the {adj} {noun} of the {noun}  — book-title grammar, not word-salad',
            len(adjs) * len(nouns) * len(nouns),
        ),
        "of": (
            "{adj} {noun} of {noun}",
            len(adjs) * len(nouns) * len(nouns),
        ),
        "paint": (
            "{adj} {adj} {noun}  — xkcd-like with real adjectives",
            len(adjs) * len(adjs) * len(nouns),
        ),
        "pgp4": (
            "PGP even-odd-even-odd (1995 cypherpunk fingerprint words)",
            256**4,
        ),
        "bip39_3": (
            "full BIP39 English 3-word (we previously only tested a tiny top-N slice)",
            2048**3,
        ),
        "name": (
            "{name}'s {adj} {noun}",
            len(load_names()) * len(adjs) * len(nouns),
        ),
    }

    if args.list:
        print(f"adjectives={len(adjs):,}  nouns={len(nouns):,}", file=sys.stderr)
        total = 0
        for name, (desc, count) in specs.items():
            print(f"{name:8} {count:14,}  {desc}")
            total += count
        print(f"{'ALL':8} {total:14,}")
        return

    if args.sample:
        for line in sample_lines(args.mode, adjs, nouns):
            print(line)
        return

    desc, count = specs[args.mode]
    print(
        f"[quality] mode={args.mode} shard={shard}/{shards} "
        f"total={count:,}  ({desc})",
        file=sys.stderr,
    )

    if args.mode == "title":
        generate_title(iter_sharded_first(adjs, shard, shards), nouns)
    elif args.mode == "of":
        generate_of(iter_sharded_first(adjs, shard, shards), nouns)
    elif args.mode == "paint":
        generate_paint(iter_sharded_first(adjs, shard, shards), adjs, nouns)
    elif args.mode == "pgp4":
        even, odd = load_pgp()
        generate_pgp4(even, odd, iter_sharded_first(even, shard, shards))
    elif args.mode == "bip39_3":
        words = load_bip39()
        generate_bip39_3(words, iter_sharded_first(words, shard, shards))
    elif args.mode == "name":
        names = load_names()
        generate_name(iter_sharded_first(names, shard, shards), adjs, nouns)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
