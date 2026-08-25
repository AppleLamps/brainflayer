#!/usr/bin/env python3
"""Convert AppleLampsX/btc Blockchair addresses to brainflayer hash160 hex."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import sys
from pathlib import Path

try:
    import base58
except ImportError as exc:
    raise SystemExit("Install base58: pip install base58") from exc

try:
    from bech32 import bech32_decode, convertbits
except ImportError as exc:
    raise SystemExit("Install bech32: pip install bech32") from exc

try:
    from huggingface_hub import hf_hub_download
except ImportError as exc:
    raise SystemExit("Install huggingface_hub: pip install huggingface_hub") from exc

DEFAULT_REPO = "AppleLampsX/btc"
DEFAULT_FILE = "blockchair_bitcoin_addresses_and_balance_LATEST.tsv.gz"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "btc_hash160.hex"


def address_to_hash160(address: str) -> str | None:
    address = address.strip()
    if not address:
        return None

    if address[0] in "13":
        try:
            payload = base58.b58decode_check(address)
        except ValueError:
            return None
        if len(payload) != 21:
            return None
        return payload[1:].hex()

    if address.lower().startswith("bc1"):
        _, data = bech32_decode(address)
        if data is None:
            return None
        version = data[0]
        program = convertbits(data[1:], 5, 8, False)
        if program is None:
            return None
        program_bytes = bytes(program)
        if version == 0 and len(program_bytes) == 20:
            return program_bytes.hex()
        return None

    return None


def resolve_input(path: Path | None, repo: str, filename: str) -> Path:
    if path is not None:
        if not path.exists():
            raise SystemExit(f"Input file not found: {path}")
        return path
    print(f"Downloading {repo}/{filename} from Hugging Face...", file=sys.stderr)
    downloaded = hf_hub_download(repo, filename, repo_type="dataset")
    return Path(downloaded)


def convert(input_path: Path, output_path: Path, dedupe: bool) -> tuple[int, int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    rows = 0
    decoded = 0
    skipped = 0

    opener = gzip.open if str(input_path).endswith(".gz") else open
    with opener(input_path, "rt", encoding="utf-8", errors="replace") as handle, output_path.open(
        "w", encoding="utf-8"
    ) as out:
        header = handle.readline()
        if not header.lower().startswith("address"):
            handle.seek(0)

        for line in handle:
            rows += 1
            address = line.split("\t", 1)[0].strip()
            hash160 = address_to_hash160(address)
            if hash160 is None:
                skipped += 1
                continue
            if dedupe:
                if hash160 in seen:
                    continue
                seen.add(hash160)
            out.write(hash160 + "\n")
            decoded += 1
            if rows % 1_000_000 == 0:
                print(
                    f"Processed {rows:,} rows, wrote {decoded:,} hash160s...",
                    file=sys.stderr,
                )

    return rows, decoded, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        help="Local Blockchair TSV(.gz); downloads from HF if omitted",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output hash160 hex file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help="Hugging Face dataset repo id",
    )
    parser.add_argument(
        "--file",
        default=DEFAULT_FILE,
        help="Address TSV filename inside the dataset repo",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Write duplicate hash160 entries",
    )
    args = parser.parse_args()

    input_path = resolve_input(args.input, args.repo, args.file)
    rows, decoded, skipped = convert(input_path, args.output, dedupe=not args.no_dedupe)
    print(
        f"Done: {rows:,} rows, {decoded:,} unique hash160s written, "
        f"{skipped:,} skipped -> {args.output}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
