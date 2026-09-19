"""Generate every ASCII upper/lower-case variant of each input line."""

import argparse
import gzip
import sys
from contextlib import nullcontext


def open_text(path, mode):
    if path == "-":
        return nullcontext(sys.stdin if "r" in mode else sys.stdout)
    if path.lower().endswith(".gz"):
        return gzip.open(path, mode + "t", encoding="utf-8", newline="")
    return open(path, mode, encoding="utf-8", newline="")


def case_variants(candidate):
    letter_positions = [
        index
        for index, character in enumerate(candidate)
        if ("a" <= character <= "z") or ("A" <= character <= "Z")
    ]
    result = list(candidate)
    for index in letter_positions:
        result[index] = result[index].lower()

    previous_gray = 0
    for counter in range(1 << len(letter_positions)):
        gray = counter ^ (counter >> 1)
        changed = gray ^ previous_gray
        if changed:
            position = (changed & -changed).bit_length() - 1
            index = letter_positions[position]
            result[index] = result[index].upper() if gray & changed else result[index].lower()
        yield "".join(result)
        previous_gray = gray


def main():
    parser = argparse.ArgumentParser(
        description="Generate every ASCII case permutation of each candidate."
    )
    parser.add_argument("input", help="Input wordlist, or - for stdin")
    parser.add_argument("output", help="Output wordlist; use a .gz suffix to compress it")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the number of variants without writing them",
    )
    parser.add_argument(
        "--max-letters",
        type=int,
        metavar="N",
        help="Skip candidates containing more than N ASCII letters",
    )
    args = parser.parse_args()
    if args.max_letters is not None and args.max_letters < 0:
        parser.error("--max-letters must be non-negative")

    total_count = 0
    candidate_count = 0
    skipped_count = 0
    variant_count = 0

    with open_text(args.input, "r") as source:
        destination_context = nullcontext(None) if args.dry_run else open_text(args.output, "w")
        with destination_context as destination:
            for raw_line in source:
                candidate = raw_line.rstrip("\r\n")
                total_count += 1
                letter_count = sum(
                    ("a" <= character <= "z") or ("A" <= character <= "Z")
                    for character in candidate
                )
                if args.max_letters is not None and letter_count > args.max_letters:
                    skipped_count += 1
                    continue

                candidate_count += 1
                candidate_variant_count = 1 << letter_count
                variant_count += candidate_variant_count

                if destination is not None:
                    for variant in case_variants(candidate):
                        destination.write(variant + "\n")

    print(
        f"Read {total_count:,} candidates; processed {candidate_count:,}; "
        f"skipped {skipped_count:,}; generated {variant_count:,} case variants.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()