#!/usr/bin/env bash
# Download the AppleLampsX/brain bloom filter (private HF dataset).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${DEST:-${ROOT}/data}"
DATASET="${DATASET:-AppleLampsX/brain}"
REVISION="${REVISION:-main}"
REMOTE_NAME="keys.blf.gz"
EXPECTED_GZ_SHA256="${EXPECTED_GZ_SHA256:-cf5b6e924aac1846a25aa97685bdf4c9a97e81de40494423616b3fba013a47a7}"
BLOOM_SIZE=$((512 * 1024 * 1024))

mkdir -p "${DEST}"
GZ="${DEST}/keys.blf.gz"
BLF="${DEST}/keys.blf"

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

if [[ ! -f "${BLF}" ]]; then
  echo "[*] decompressing ${GZ}"
  gzip -dc "${GZ}" > "${BLF}"
fi

sz="$(stat -c%s "${BLF}")"
if [[ "${sz}" -ne "${BLOOM_SIZE}" ]]; then
  echo "unexpected bloom size ${sz} (expected ${BLOOM_SIZE})" >&2
  exit 1
fi

echo "[+] ${BLF} ready ($(numfmt --to=iec-i --suffix=B "${sz}" 2>/dev/null || echo "${sz} bytes"))"
