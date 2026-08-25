#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIBLE="${ROOT}/data/kjv.json"
BLOOM="${ROOT}/example.blf"
BRAINFLAYER="${ROOT}/brainflayer"

if [[ "${1:-}" == "-b" && -n "${2:-}" ]]; then
  BLOOM="$2"
  shift 2
elif [[ -f "${1:-}" && "${1##*.}" == "blf" ]]; then
  BLOOM="$1"
  shift
fi

if [[ ! -x "${BRAINFLAYER}" ]]; then
  echo "brainflayer binary not found; run 'make' in ${ROOT}" >&2
  exit 1
fi

if [[ ! -f "${BLOOM}" ]]; then
  echo "Bloom filter not found: ${BLOOM}" >&2
  echo "Create one with: ./hex2blf example.hex example.blf" >&2
  exit 1
fi

if [[ ! -f "${BIBLE}" ]]; then
  python3 "${ROOT}/scripts/fetch_bible.py" -o "${BIBLE}"
fi

python3 "${ROOT}/scripts/bible_seedgen.py" "$@" | \
  "${BRAINFLAYER}" -v -b "${BLOOM}"
