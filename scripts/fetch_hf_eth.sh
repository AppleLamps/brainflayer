#!/usr/bin/env bash
# Download AppleLampsX/eth (funded Ethereum addresses) and build -b/-f files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DEST:-${ROOT}/data}"
DATASET="${DATASET:-AppleLampsX/eth}"
REVISION="${REVISION:-main}"
REMOTE_NAME="ethereum.hex.gz"
EXPECTED_GZ_SHA256="${EXPECTED_GZ_SHA256:-34306bb03329d0215f5bbeb2169fbf1fca1e846e0d3c43cf08d0c6063afbd6ea}"
HEX2BLF="${HEX2BLF:-${ROOT}/hex2blf}"
BLOOM_SIZE=$((512 * 1024 * 1024))

mkdir -p "${DEST}"
GZ="${DEST}/ethereum.hex.gz"
HEX="${DEST}/ethereum.hex"
SORTED="${DEST}/ethereum.sorted.hex"
BIN="${DEST}/eth.bin"
BLF="${DEST}/eth.blf"

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

need_hex=0
if [[ ! -f "${BLF}" || "$(stat -c%s "${BLF}")" -ne "${BLOOM_SIZE}" ]]; then
  need_hex=1
fi
if [[ ! -f "${BIN}" ]]; then
  need_hex=1
fi

if [[ "${need_hex}" -eq 1 && ! -f "${HEX}" ]]; then
  echo "[*] decompressing ${GZ}"
  gzip -dc "${GZ}" > "${HEX}"
fi

if [[ ! -f "${BLF}" || "$(stat -c%s "${BLF}")" -ne "${BLOOM_SIZE}" ]]; then
  if [[ ! -x "${HEX2BLF}" ]]; then
    echo "missing ${HEX2BLF}; run make hex2blf" >&2
    exit 1
  fi
  echo "[*] building bloom filter ${BLF}"
  "${HEX2BLF}" "${HEX}" "${BLF}"
fi

if [[ ! -f "${BIN}" ]]; then
  echo "[*] sorting unique addresses for -f"
  # Keep sort spill on the data volume; /tmp may be a small tmpfs.
  TMPDIR="${DEST}" LC_ALL=C sort -S 2G -u -o "${SORTED}" "${HEX}"
  echo "[*] converting ${SORTED} -> ${BIN}"
  python3 - "${SORTED}" "${BIN}" <<'PY'
import sys
from pathlib import Path

src, dest = Path(sys.argv[1]), Path(sys.argv[2])
tmp = dest.with_suffix(dest.suffix + ".tmp")
prev = None
count = 0
with src.open("rt", encoding="ascii") as inf, tmp.open("wb", buffering=8 << 20) as out:
    for raw in inf:
        line = raw.strip().lower()
        if line.startswith("0x"):
            line = line[2:]
        if len(line) != 40:
            raise SystemExit(f"bad address line {count + 1}: {line!r}")
        blob = bytes.fromhex(line)
        if prev is not None and blob <= prev:
            raise SystemExit(f"address list is not strictly sorted at line {count + 1}")
        out.write(blob)
        prev = blob
        count += 1
tmp.replace(dest)
print(f"[+] wrote {dest} ({count} records)", file=sys.stderr)
PY
  rm -f "${SORTED}"
fi

rm -f "${HEX}"

sz="$(stat -c%s "${BIN}")"
count=$((sz / 20))
if [[ $((sz % 20)) -ne 0 ]]; then
  echo "unexpected ${BIN} size ${sz} (not a multiple of 20)" >&2
  exit 1
fi
if [[ "$(stat -c%s "${BLF}")" -ne "${BLOOM_SIZE}" ]]; then
  echo "unexpected ${BLF} size" >&2
  exit 1
fi

echo "[+] ${BIN} ready ($(numfmt --to=iec-i --suffix=B "${sz}" 2>/dev/null || echo "${sz} bytes"), ${count} addresses)"
echo "[+] ${BLF} ready"
