#!/usr/bin/env python3
"""Verify the brainflayer search pipeline is wired correctly.

Checks address decoding, bloom membership, planted-passphrase hits,
and that known brainwallet hash160s are (or are not) in the BTC dump.
"""

from __future__ import annotations

import mmap
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from addresses_to_hash160 import address_to_hash160  # noqa: E402

BLOOM_SIZE = 512 * 1024 * 1024
BTC_HEX = ROOT / "data" / "btc_hash160.hex"
BTC_BLF = ROOT / "data" / "btc.blf"
SEEDS = ROOT / "data" / "seed_candidates.txt"
BRAINFLAYER = ROOT / "brainflayer"
HEX2BLF = ROOT / "hex2blf"

# BIP173 / well-known vectors
GENESIS_ADDR = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
GENESIS_H160 = "62e907b15cbf27d5425399ebf6f0fb50ebb88f18"
P2WPKH_ADDR = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
P2WPKH_H160 = "751e76e8199196d454941c45d1b3a323f1433bd6"

# Historic drained brainwallets (uncompressed P2PKH).
# Presence in a *balance* dump is optional; absence is not a search failure.
KNOWN_BRAINWALLETS = [
    "password",
    "correct horse battery staple",
    "satoshi",
    "hello world",
    "bitcoin",
]
# Famous CHBS uncompressed P2PKH (Ryan Castellucci / DEFCON).
CHBS_ADDR = "1JwSSubhmg6iPtRjtyqhUYYH7bZg3Lfy1T"
CHBS_H160 = "c4c5d791fcb4654a1ef5e03fe0ad3d9c598f9827"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def _bh_fns() -> list:
    # Must match bloom.h BH00..BH19 on little-endian uint32_t[5].
    return [
        lambda n: n[0],
        lambda n: n[1],
        lambda n: n[2],
        lambda n: n[3],
        lambda n: n[4],
        lambda n: (n[0] << 16 | n[1] >> 16) & 0xFFFFFFFF,
        lambda n: (n[1] << 16 | n[2] >> 16) & 0xFFFFFFFF,
        lambda n: (n[2] << 16 | n[3] >> 16) & 0xFFFFFFFF,
        lambda n: (n[3] << 16 | n[4] >> 16) & 0xFFFFFFFF,
        lambda n: (n[4] << 16 | n[0] >> 16) & 0xFFFFFFFF,
        lambda n: (n[0] << 8 | n[1] >> 24) & 0xFFFFFFFF,
        lambda n: (n[1] << 8 | n[2] >> 24) & 0xFFFFFFFF,
        lambda n: (n[2] << 8 | n[3] >> 24) & 0xFFFFFFFF,
        lambda n: (n[3] << 8 | n[4] >> 24) & 0xFFFFFFFF,
        lambda n: (n[4] << 8 | n[0] >> 24) & 0xFFFFFFFF,
        lambda n: (n[0] << 24 | n[1] >> 8) & 0xFFFFFFFF,
        lambda n: (n[1] << 24 | n[2] >> 8) & 0xFFFFFFFF,
        lambda n: (n[2] << 24 | n[3] >> 8) & 0xFFFFFFFF,
        lambda n: (n[3] << 24 | n[4] >> 8) & 0xFFFFFFFF,
        lambda n: (n[4] << 24 | n[0] >> 8) & 0xFFFFFFFF,
    ]


def bloom_contains_hash160(blf_path: Path, h160_hex: str) -> bool:
    raw = bytes.fromhex(h160_hex)
    words = list(struct.unpack("<5I", raw))
    with blf_path.open("rb") as handle:
        bloom = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            for fn in _bh_fns():
                bit = fn(words)
                if ((bloom[bit >> 3] >> (bit & 7)) & 1) == 0:
                    return False
            return True
        finally:
            bloom.close()


def bloom_bits_set(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) != BLOOM_SIZE:
        fail(f"{path} size {len(data)} != {BLOOM_SIZE}")
    ones = 0
    sample = data[:: 1024 * 1024]  # 512 samples, 1 per MB
    nonempty_pages = sum(1 for b in sample if b != 0)
    # popcount of a 1MB stride is enough to prove the filter isn't empty/all-ones
    for byte in sample:
        ones += byte.bit_count()
    return nonempty_pages, ones


def python_hash160_in_hex(h160: str, hex_path: Path) -> bool:
    proc = subprocess.run(
        ["grep", "-F", "-m", "1", "-x", h160.lower(), str(hex_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def run_brainflayer(
    bloom: Path | None,
    phrases: list[str],
    extra_args: list[str] | None = None,
) -> list[str]:
    extra_args = extra_args or []
    cmd = [str(BRAINFLAYER), "-c", "uc", *extra_args]
    if bloom is not None:
        cmd.extend(["-b", str(bloom)])
    proc = subprocess.run(
        cmd,
        input="\n".join(phrases) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        fail(
            f"brainflayer exited {proc.returncode}: {proc.stderr[-2000:]}"
        )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def parse_generate_line(line: str) -> tuple[str, str, str, str]:
    # hash160:u|c:sha256:passphrase
    h160, kind, mode, phrase = line.split(":", 3)
    return h160, kind, mode, phrase


def main() -> None:
    print("=== 1. Tools and data files ===")
    for path in (BRAINFLAYER, HEX2BLF, BTC_HEX, BTC_BLF, SEEDS):
        if not path.exists():
            fail(f"missing {path}")
        ok(f"{path.name} exists ({path.stat().st_size:,} bytes)")

    nonempty, ones = bloom_bits_set(BTC_BLF)
    if nonempty == 0:
        fail("btc.blf appears empty (no bits set in 1MB-stride sample)")
    if nonempty == 512 and ones == 512 * 8:
        fail("btc.blf sample looks all-ones (would match everything)")
    ok(f"btc.blf populated: {nonempty}/512 sampled megabyte pages nonzero")

    print("\n=== 2. Address -> hash160 vectors ===")
    got = address_to_hash160(GENESIS_ADDR)
    if got != GENESIS_H160:
        fail(f"genesis hash160 {got} != {GENESIS_H160}")
    ok(f"genesis P2PKH decodes to {GENESIS_H160}")

    got = address_to_hash160(P2WPKH_ADDR)
    if got != P2WPKH_H160:
        fail(f"P2WPKH hash160 {got} != {P2WPKH_H160}")
    ok(f"BIP173 P2WPKH decodes to {P2WPKH_H160}")

    if address_to_hash160("bc1p5d7rjq7g6rdk2yhzks9smlaqtedr4dekq08ge8ztwac72sfr9rusxg3297"):
        fail("taproot (bc1p) should be skipped — not a hash160 pubkey hash")
    ok("taproot addresses skipped")

    print("\n=== 3. BTC dump membership (hex file is bloom source of truth) ===")
    if not python_hash160_in_hex(GENESIS_H160, BTC_HEX):
        fail("genesis hash160 missing from btc_hash160.hex — dump/conversion is wrong")
    ok("genesis hash160 is in btc_hash160.hex")
    if not bloom_contains_hash160(BTC_BLF, GENESIS_H160):
        fail("genesis hash160 is in the hex dump but NOT in data/btc.blf")
    ok("genesis hash160 is present in data/btc.blf (all 20 bloom bits set)")

    print("\n=== 4. brainflayer generate mode (no bloom) ===")
    generated = run_brainflayer(None, ["password"])
    if len(generated) != 2:
        fail(f"expected 2 hash160s (u+c) for 'password', got {generated}")
    kinds = {parse_generate_line(line)[1] for line in generated}
    if kinds != {"u", "c"}:
        fail(f"expected kinds u,c got {kinds} from {generated}")
    ok(f"generate mode: {generated[0]}")
    ok(f"generate mode: {generated[1]}")

    chbs_rows = run_brainflayer(None, ["correct horse battery staple"])
    chbs_u = next(h for h, k, _, _ in (parse_generate_line(l) for l in chbs_rows) if k == "u")
    decoded_chbs = address_to_hash160(CHBS_ADDR)
    if decoded_chbs != CHBS_H160:
        fail(f"CHBS address decode {decoded_chbs} != {CHBS_H160}")
    if chbs_u != CHBS_H160:
        fail(f"brainflayer SHA256('correct horse battery staple') {chbs_u} != famous {CHBS_H160}")
    ok(f"SHA256 brainwallet matches famous CHBS address {CHBS_ADDR}")

    print("\n=== 5. Planted-passphrase positive control ===")
    control_phrase = "brainflayer-pipeline-self-test-426d"
    control_rows = run_brainflayer(None, [control_phrase])
    control_h160s = [parse_generate_line(line)[0] for line in control_rows]
    if len(control_h160s) != 2:
        fail(f"control generate failed: {control_rows}")

    with tempfile.TemporaryDirectory(prefix="bf-verify-") as tmp:
        tmp_path = Path(tmp)
        hex_path = tmp_path / "control.hex"
        blf_path = tmp_path / "control.blf"
        hex_path.write_text("\n".join(control_h160s) + "\n")
        built = subprocess.run(
            [str(HEX2BLF), str(hex_path), str(blf_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if built.returncode != 0:
            fail(f"hex2blf failed: {built.stderr}")
        decoys = [
            "this is not the control phrase",
            "password",
            "correct horse battery staple",
            control_phrase,
            "another decoy",
        ]
        hits = run_brainflayer(blf_path, decoys)
        hit_phrases = {parse_generate_line(line)[3] for line in hits}
        if control_phrase not in hit_phrases:
            fail(f"planted phrase was NOT found. hits={hits}")
        if any(p != control_phrase for p in hit_phrases):
            fail(f"unexpected extra hits: {hits}")
        if len(hits) != 2:
            fail(f"expected 2 hits (u+c) for planted phrase, got {hits}")
        ok(f"planted phrase found ({len(hits)} hits, uncompressed+compressed)")

        # Negative: same phrases against an empty-ish bloom of unrelated hashes
        other_hex = tmp_path / "other.hex"
        other_blf = tmp_path / "other.blf"
        other_hex.write_text(GENESIS_H160 + "\n")
        subprocess.run(
            [str(HEX2BLF), str(other_hex), str(other_blf)],
            check=True,
            capture_output=True,
        )
        misses = run_brainflayer(other_blf, decoys)
        if misses:
            fail(f"decoy phrases matched genesis-only bloom: {misses}")
        ok("unrelated phrases do not match a genesis-only bloom")

    print("\n=== 6. Real BTC bloom: known brainwallets ===")
    bw_hits = run_brainflayer(BTC_BLF, KNOWN_BRAINWALLETS)
    if bw_hits:
        ok(f"known brainwallets HIT on-chain bloom ({len(bw_hits)}):")
        for line in bw_hits:
            print(f"  HIT {line}")
    else:
        ok("no hits for classic drained brainwallets (expected if dump is balance-only or they are empty)")

    in_dump = []
    for phrase in KNOWN_BRAINWALLETS:
        rows = run_brainflayer(None, [phrase])
        for line in rows:
            h160, kind, _, _ = parse_generate_line(line)
            present = python_hash160_in_hex(h160, BTC_HEX)
            status = "IN DUMP" if present else "not in dump"
            print(f"  {phrase!r} [{kind}] {h160} -> {status}")
            if present:
                in_dump.append((phrase, kind, h160))

    if in_dump and not bw_hits:
        fail(
            "brainwallet hash160 is in btc_hash160.hex but bloom search missed it "
            f"{in_dump}"
        )
    if in_dump:
        ok("hash160s present in dump were also found via bloom search")

    print("\n=== 7. Real BTC bloom: seed file contains planted control? ===")
    # Confirm 'password' is actually in the seed list we searched.
    password_in_seeds = False
    with SEEDS.open("rb") as handle:
        for line in handle:
            if line == b"password\n":
                password_in_seeds = True
                break
    if not password_in_seeds:
        fail("seed_candidates.txt does not contain exact line 'password'")
    ok("seed list contains 'password' as an exact line")

    print("\n=== 8. Verbose counter matches input lines ===")
    sample = ["verbose-count-check"] * 5000
    proc = subprocess.run(
        [str(BRAINFLAYER), "-v", "-c", "uc", "-b", str(BTC_BLF), "-N", "5000"],
        input="\n".join(sample) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        fail(f"verbose counter run failed: {proc.stderr[-1000:]}")
    reported = None
    for line in proc.stderr.replace("\r", "\n").splitlines():
        if "found:" in line:
            # rate: ... found:     0/5000       elapsed: ...
            try:
                reported = int(line.split("found:", 1)[1].split("/", 1)[1].split()[0])
            except (IndexError, ValueError):
                continue
    if reported != 5000:
        fail(f"verbose counter reported {reported} lines, expected 5000")
    ok("verbose progress counter equals the number of passphrases (not 2x)")

    print("\n=== RESULT: search pipeline is working ===")
    print("brainflayer SHA256(passphrase) -> privkey -> compressed+uncompressed")
    print("hash160 lookup against data/btc.blf is correct.")
    print("0 hits on the full seed list means none of those passphrases currently")
    print("match a hash160 in the AppleLampsX/btc address dump — not a wiring bug.")


if __name__ == "__main__":
    main()
