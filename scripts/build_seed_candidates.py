#!/usr/bin/env python3
"""Build a unified, high-quality brainwallet seed candidate list for brainflayer."""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from bible_seedgen import DEFAULT_BIBLE, generate_candidates as generate_bible_candidates, load_bible
from quran_seedgen import DEFAULT_QURAN, generate_candidates as generate_quran_candidates, load_quran
from dict_phrases import DEFAULT_PHRASE_LENGTHS, DEFAULT_PHRASE_TOP_N, iter_dictionary_phrases
from seed_variants import expand_variants

DEFAULT_BITCOINTALK_CANDIDATES = [
    ROOT / "uploads" / "bitcointalk_signatures_only_2012_2016_ffa2.csv",
    Path("/home/ubuntu/.cursor/projects/workspace/uploads")
    / "bitcointalk_signatures_only_2012_2016_ffa2.csv",
]
DEFAULT_OUTPUT = ROOT / "data" / "seed_candidates.txt"
DEFAULT_MANIFEST = ROOT / "data" / "seed_candidates.manifest.tsv"
DICT_DIR = ROOT / "data" / "dict"
DICT_FILES = {
    "en": DICT_DIR / "english.txt",
    "ru": DICT_DIR / "russian.txt",
    "zh": DICT_DIR / "chinese.txt",
}
DICT_PHRASE_FILES = {
    "en": DICT_DIR / "english_phrase.txt",
    "ru": DICT_DIR / "russian.txt",
    "zh": DICT_DIR / "chinese.txt",
}

EXTRA_SEEDS = [
    "bitcoin",
    "Bitcoin",
    "satoshi",
    "Satoshi",
    "satoshi nakamoto",
    "Satoshi Nakamoto",
    "password",
    "Password",
    "brainwallet",
    "hello world",
    "correct horse battery staple",
    "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks",
    "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks.",
    "In God we trust",
    "To the moon",
    "HODL",
    "hodl",
    "lambo",
    "When lambo",
    "magic internet money",
    "vires in numeris",
    "Vires in numeris",
    "genesis block",
    "Genesis block",
]

# High-yield Bible modes: skip single-word and space-stripped variants (noisy).
BIBLE_MODES = {"reference", "text", "nopunct", "ref_text", "prefix"}
QURAN_MODES = {
    "reference",
    "text",
    "nodiac",
    "nospaces",
    "nopunct",
    "ref_text",
    "prefix",
    "bismillah",
}


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_outer_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1].strip()
    return text


def strip_punctuation(text: str) -> str:
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("S"):
            cleaned.append(" ")
        else:
            cleaned.append(char)
    return normalize_ws("".join(cleaned))


def is_prose_line(line: str) -> bool:
    line = normalize_ws(line)
    if len(line) < 4:
        return False
    letters = sum(ch.isalpha() for ch in line)
    if letters / len(line) < 0.35:
        return False
    if re.fullmatch(r"[\W_]+", line):
        return False
    box_chars = sum(ch in "─│┌┐└┘├┤┬┴┼═║╔╗╚╝█▇▆▅▄▃▂▁" for ch in line)
    if box_chars > max(3, len(line) // 8):
        return False
    return True


def prose_only(text: str) -> str:
    lines = [normalize_ws(line) for line in text.splitlines()]
    prose = [line for line in lines if is_prose_line(line)]
    return normalize_ws(" ".join(prose))


def add_variant(seen: set[str], manifest: list[tuple[str, str]], source: str, value: str) -> None:
    candidate = value.strip()
    if not candidate or len(candidate) > 4096 or candidate in seen:
        return
    seen.add(candidate)
    manifest.append((source, candidate))


def add_variants(
    seen: set[str],
    manifest: list[tuple[str, str]],
    source: str,
    text: str,
    *,
    include_nopunct: bool = True,
    include_truncations: bool = False,
) -> None:
    base = normalize_ws(text)
    if not base:
        return

    nopunct = strip_punctuation(base) if include_nopunct else None
    for variant in expand_variants(base, nopunct=nopunct):
        add_variant(seen, manifest, source, variant)

    if include_truncations and len(base) > 64:
        for n in (32, 64, 128, 256):
            if len(base) >= n:
                truncated = base[:n]
                truncated_nopunct = strip_punctuation(truncated) if include_nopunct else None
                for variant in expand_variants(truncated, nopunct=truncated_nopunct):
                    add_variant(seen, manifest, source + f":trunc{n}", variant)


def iter_bitcointalk(path: Path) -> list[str]:
    if not path.exists():
        return []
    signatures: list[str] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            sig = strip_outer_quotes(row.get("signature", "").strip())
            if sig:
                signatures.append(sig)
    return signatures


def add_bitcointalk_candidates(
    seen: set[str],
    manifest: list[tuple[str, str]],
    signatures: list[str],
) -> None:
    for index, sig in enumerate(signatures):
        source = f"bitcointalk:{index}"
        add_variants(seen, manifest, source, sig, include_truncations=True)

        prose = prose_only(sig)
        if prose and prose != normalize_ws(sig):
            add_variants(seen, manifest, source + ":prose", prose, include_truncations=True)

        for match in re.finditer(r'"([^"\n]{4,240})"|\'([^\'\n]{4,240})\'', sig):
            quoted = match.group(1) or match.group(2)
            add_variants(seen, manifest, source + ":quote", quoted)

        for line in sig.splitlines():
            line = normalize_ws(line)
            if is_prose_line(line):
                add_variants(seen, manifest, source + ":line", line)

        for match in re.finditer(
            r"Quote from:.*?\n(.*?)(?:\n\n|\nQuote from:|\Z)",
            sig,
            flags=re.DOTALL | re.IGNORECASE,
        ):
            quoted_block = prose_only(match.group(1))
            if quoted_block:
                add_variants(seen, manifest, source + ":quote_block", quoted_block)

        for match in re.finditer(r"https?://[^\s\]]+|topic=\d+", sig):
            add_variant(seen, manifest, source + ":url", match.group(0))


def add_bible_candidates(seen: set[str], manifest: list[tuple[str, str]], bible_path: Path) -> None:
    bible = load_bible(bible_path)
    for candidate in generate_bible_candidates(
        bible,
        modes=BIBLE_MODES,
        books=None,
        chapters=None,
        max_words=7,
    ):
        add_variant(seen, manifest, "bible", candidate)


def add_quran_candidates(seen: set[str], manifest: list[tuple[str, str]], quran_path: Path) -> None:
    quran = load_quran(quran_path)
    for candidate in generate_quran_candidates(
        quran,
        modes=QURAN_MODES,
        surahs=None,
        max_words=7,
    ):
        add_variant(seen, manifest, "quran", candidate)


def add_extra_candidates(seen: set[str], manifest: list[tuple[str, str]]) -> None:
    for seed in EXTRA_SEEDS:
        add_variants(seen, manifest, "extra", seed, include_truncations=False)


def load_dictionary_words(path: Path) -> list[str]:
    if not path.exists():
        return []
    words: list[str] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            word = line.strip()
            if word and not word.startswith("#"):
                words.append(word)
    return words


def add_dictionary_candidates(
    seen: set[str],
    manifest: list[tuple[str, str]],
    dict_dir: Path,
    phrase_top_n: dict[int, int] | None = None,
    phrase_lengths: tuple[int, ...] = DEFAULT_PHRASE_LENGTHS,
) -> None:
    limits = phrase_top_n or DEFAULT_PHRASE_TOP_N
    for language, default_path in DICT_FILES.items():
        path = dict_dir / default_path.name
        if not path.exists():
            path = default_path
        words = load_dictionary_words(path)
        if not words:
            print(f"Warning: dictionary not found or empty: {path}", file=sys.stderr)
            continue
        print(f"Adding {len(words):,} {language} dictionary words...", file=sys.stderr)
        for word in words:
            for variant in expand_variants(word):
                add_variant(seen, manifest, f"dict:{language}", variant)

    for language, default_path in DICT_PHRASE_FILES.items():
        path = dict_dir / default_path.name
        if not path.exists():
            path = default_path
        words = load_dictionary_words(path)
        if not words:
            print(f"Warning: phrase base not found or empty: {path}", file=sys.stderr)
            continue
        phrase_count = 0
        print(
            f"Adding {language} dictionary phrases (lengths {phrase_lengths}, pools {limits})...",
            file=sys.stderr,
        )
        for phrase in iter_dictionary_phrases(
            words,
            phrase_lengths=phrase_lengths,
            top_n_by_length=limits,
        ):
            phrase_count += 1
            for variant in expand_variants(phrase):
                add_variant(seen, manifest, f"dict:{language}:phrase", variant)
        print(f"  generated {phrase_count:,} base phrases for {language}", file=sys.stderr)


def resolve_bitcointalk_path(path: Path | None) -> Path | None:
    if path is not None:
        return path if path.exists() else None
    for candidate in DEFAULT_BITCOINTALK_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def build_seed_list(
    bible_path: Path,
    quran_path: Path,
    dict_dir: Path,
    bitcointalk_path: Path | None,
    include_bible: bool,
    include_quran: bool,
    include_dictionaries: bool,
    include_bitcointalk: bool,
    include_extras: bool,
    phrase_top_n: dict[int, int] | None = None,
    phrase_lengths: tuple[int, ...] = DEFAULT_PHRASE_LENGTHS,
) -> list[tuple[str, str]]:
    seen: set[str] = set()
    manifest: list[tuple[str, str]] = []

    if include_extras:
        add_extra_candidates(seen, manifest)
    if include_dictionaries:
        add_dictionary_candidates(
            seen,
            manifest,
            dict_dir,
            phrase_top_n=phrase_top_n,
            phrase_lengths=phrase_lengths,
        )
    if include_bitcointalk:
        resolved = resolve_bitcointalk_path(bitcointalk_path)
        if resolved is None:
            print("Warning: Bitcointalk CSV not found; skipping signatures.", file=sys.stderr)
        else:
            signatures = iter_bitcointalk(resolved)
            add_bitcointalk_candidates(seen, manifest, signatures)
    if include_bible:
        add_bible_candidates(seen, manifest, bible_path)
    if include_quran:
        add_quran_candidates(seen, manifest, quran_path)

    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Seed candidate output file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Source manifest TSV (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--bible",
        type=Path,
        default=DEFAULT_BIBLE,
        help="KJV JSON path",
    )
    parser.add_argument(
        "--quran",
        type=Path,
        default=DEFAULT_QURAN,
        help="Arabic Quran JSON path",
    )
    parser.add_argument(
        "--dict-dir",
        type=Path,
        default=DICT_DIR,
        help="Directory containing english.txt, russian.txt, chinese.txt",
    )
    parser.add_argument(
        "--no-dictionaries",
        action="store_true",
        help="Skip English/Russian/Chinese dictionary words and phrases",
    )
    parser.add_argument(
        "--dict-phrase-lengths",
        default="2,3,4,5",
        help="Comma-separated dictionary phrase lengths (default: 2,3,4,5)",
    )
    parser.add_argument(
        "--dict-phrase-top-n",
        default="2:500,3:80,4:35,5:18",
        help="Phrase pool sizes per length, e.g. 2:500,3:80,4:35,5:18",
    )
    parser.add_argument(
        "--bitcointalk",
        type=Path,
        default=None,
        help="Bitcointalk signatures CSV (auto-detected if omitted)",
    )
    parser.add_argument(
        "--no-bible",
        action="store_true",
        help="Skip Bible-derived candidates",
    )
    parser.add_argument(
        "--no-quran",
        action="store_true",
        help="Skip Arabic Quran-derived candidates",
    )
    parser.add_argument(
        "--no-bitcointalk",
        action="store_true",
        help="Skip Bitcointalk signature candidates",
    )
    parser.add_argument(
        "--no-extras",
        action="store_true",
        help="Skip common extra crypto/brainwallet phrases",
    )
    args = parser.parse_args()

    phrase_lengths = tuple(
        int(part.strip())
        for part in args.dict_phrase_lengths.split(",")
        if part.strip()
    )
    phrase_top_n: dict[int, int] = {}
    for part in args.dict_phrase_top_n.split(","):
        if not part.strip():
            continue
        length_str, size_str = part.split(":", 1)
        phrase_top_n[int(length_str.strip())] = int(size_str.strip())

    manifest = build_seed_list(
        bible_path=args.bible,
        quran_path=args.quran,
        dict_dir=args.dict_dir,
        bitcointalk_path=args.bitcointalk,
        include_bible=not args.no_bible,
        include_quran=not args.no_quran,
        include_dictionaries=not args.no_dictionaries,
        include_bitcointalk=not args.no_bitcointalk,
        include_extras=not args.no_extras,
        phrase_top_n=phrase_top_n,
        phrase_lengths=phrase_lengths,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for _, candidate in manifest:
            handle.write(candidate + "\n")

    with args.manifest.open("w", encoding="utf-8") as handle:
        handle.write("source\tcandidate\n")
        for source, candidate in manifest:
            escaped = candidate.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")
            handle.write(f"{source}\t{escaped}\n")

    counts: dict[str, int] = {}
    for source, _ in manifest:
        bucket = source.split(":", 1)[0]
        counts[bucket] = counts.get(bucket, 0) + 1

    print(f"Wrote {len(manifest):,} candidates -> {args.output}", file=sys.stderr)
    print(f"Manifest -> {args.manifest}", file=sys.stderr)
    for bucket, count in sorted(counts.items()):
        print(f"  {bucket}: {count:,}", file=sys.stderr)


if __name__ == "__main__":
    main()
