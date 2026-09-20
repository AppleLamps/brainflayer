#!/usr/bin/env python3
"""Binary-search a sorted 20-byte hash160 file (brainflayer -f format)."""

from __future__ import annotations

import argparse
import mmap
import sys
from pathlib import Path

HASHLEN = 20


def lookup(path: Path, digest: bytes) -> bool:
    with path.open("rb") as handle:
        mem = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            if len(mem) % HASHLEN:
                raise SystemExit(f"{path} size {len(mem)} is not a multiple of {HASHLEN}")
            lo, hi = 0, len(mem) // HASHLEN - 1
            while lo <= hi:
                mid = (lo + hi) // 2
                item = mem[mid * HASHLEN : (mid + 1) * HASHLEN]
                if item == digest:
                    return True
                if item < digest:
                    lo = mid + 1
                else:
                    hi = mid - 1
            return False
        finally:
            mem.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binfile", type=Path, help="sorted hash160 binary (e.g. data/h160.bin)")
    parser.add_argument("hash160", nargs="+", help="40-digit hex hash160(s)")
    args = parser.parse_args(argv)
    rc = 0
    for raw in args.hash160:
        hexes = raw.strip().lower()
        if len(hexes) != 40:
            print(f"bad hash160: {raw}", file=sys.stderr)
            rc = 2
            continue
        present = lookup(args.binfile, bytes.fromhex(hexes))
        print(f"{hexes} {'found' if present else 'absent'}")
        if not present:
            rc = max(rc, 1)
    return rc


if __name__ == "__main__":
    sys.exit(main())
