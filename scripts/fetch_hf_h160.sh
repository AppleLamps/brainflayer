#!/usr/bin/env bash
# Download AppleLampsX/h160 (exact hash160 list) and convert to brainflayer -f binary.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DEST:-${ROOT}/data}"
DATASET="${DATASET:-AppleLampsX/h160}"
REVISION="${REVISION:-main}"
REMOTE_NAME="all.hex.gz"
EXPECTED_GZ_SHA256="${EXPECTED_GZ_SHA256:-9af7b1cd9a42fd4bbaab8ae8b84d230e81d9fe6a1f3b440dbcef6eadd8ad4cc0}"
EXPECTED_COUNT="${EXPECTED_COUNT:-90379448}"
EXPECTED_BIN_SIZE=$((EXPECTED_COUNT * 20))

mkdir -p "${DEST}"
GZ="${DEST}/all.hex.gz"
BIN="${DEST}/h160.bin"

if [[ -z "${HF_TOKEN:-}" ]]; then
  echo "HF_TOKEN is required to download ${DATASET} (private dataset)" >&2
  exit 1
fi

if [[ ! -f "${GZ}" ]]; then
  echo "[*] downloading ${DATASET}/${REMOTE_NAME}"
  curl -L --fail --retry 4 --retry-delay 4 \
    -H "Authorization: Bearer ${HF_TOKEN}" \
    -o "${GZ}" \
    "https://huggingface.co/datasets/${DATASET}/resolve/${REVISION}/${REMOTE_NAME}"
fi

got="$(sha256sum "${GZ}" | awk '{print $1}')"
if [[ "${got}" != "${EXPECTED_GZ_SHA256}" ]]; then
  echo "checksum mismatch for ${GZ}: got ${got} expected ${EXPECTED_GZ_SHA256}" >&2
  exit 1
fi

if [[ ! -f "${BIN}" || "$(stat -c%s "${BIN}")" -ne "${EXPECTED_BIN_SIZE}" ]]; then
  echo "[*] converting ${GZ} -> ${BIN} (${EXPECTED_COUNT} x 20-byte hash160s)"
  python3 - "${GZ}" "${BIN}" "${EXPECTED_COUNT}" <<'PY'
import gzip, sys
from pathlib import Path

gz, dest, expect = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
tmp = dest.with_suffix(dest.suffix + ".tmp")
prev = None
count = 0
with gzip.open(gz, "rt", encoding="ascii") as src, tmp.open("wb", buffering=8 << 20) as out:
    for raw in src:
        line = raw.strip().lower()
        if len(line) != 40:
            raise SystemExit(f"bad hash160 line {count + 1}: {line!r}")
        blob = bytes.fromhex(line)
        if prev is not None and blob <= prev:
            raise SystemExit(f"hash160 list is not strictly sorted at line {count + 1}")
        out.write(blob)
        prev = blob
        count += 1
if count != expect:
    raise SystemExit(f"record count {count} != {expect}")
tmp.replace(dest)
print(f"[+] wrote {dest} ({count} records)", file=sys.stderr)
PY
fi

sz="$(stat -c%s "${BIN}")"
if [[ "${sz}" -ne "${EXPECTED_BIN_SIZE}" ]]; then
  echo "unexpected ${BIN} size ${sz} (expected ${EXPECTED_BIN_SIZE})" >&2
  exit 1
fi

echo "[+] ${BIN} ready ($(numfmt --to=iec-i --suffix=B "${sz}" 2>/dev/null || echo "${sz} bytes"), ${EXPECTED_COUNT} hash160s)"
