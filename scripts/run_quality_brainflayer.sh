#!/usr/bin/env bash
# Stream a quality multi-billion seed mode into one brainflayer process per CPU.
# Usage: scripts/run_quality_brainflayer.sh [mode] [-o HITS] [-- extra brainflayer args]
# Modes: title (default), of, paint, pgp4, bip39_3, name
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAINFLAYER="${ROOT}/brainflayer"
ECMTABGEN="${ROOT}/ecmtabgen"
BLOOM="${ROOT}/data/btc.blf"
TABLE="${ROOT}/data/ecmult.w16.tab"
WINDOW=16
THREADS="${BF_PROCS:-$(nproc)}"
OUTFILE=""
MODE="title"

if [[ $# -gt 0 && "$1" != -* ]]; then
  MODE="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    -b) BLOOM="$2"; shift 2 ;;
    -j) THREADS="$2"; shift 2 ;;
    -o) OUTFILE="$2"; shift 2 ;;
    --) shift; break ;;
    -h|--help)
      echo "Usage: $0 [mode] [-b BLOOM] [-j PROCS] [-o OUT] [-- extra brainflayer args]" >&2
      echo "Modes: title of paint pgp4 bip39_3 name" >&2
      exit 1
      ;;
    *) break ;;
  esac
done

if [[ ! -x "${BRAINFLAYER}" ]]; then
  echo "brainflayer binary not found; run 'make' in ${ROOT}" >&2
  exit 1
fi
if [[ ! -f "${BLOOM}" ]]; then
  echo "Bloom filter not found: ${BLOOM}" >&2
  exit 1
fi
if [[ "${THREADS}" -lt 1 ]]; then
  echo "Invalid process count: ${THREADS}" >&2
  exit 1
fi
if [[ ! -f "${TABLE}" ]]; then
  echo "[*] Building ecmult table ${TABLE} (window ${WINDOW})..." >&2
  "${ECMTABGEN}" "${WINDOW}" "${TABLE}"
fi

python3 -u "${ROOT}/scripts/quality_seedgen.py" --list >&2

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bf-quality.XXXXXX")"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

echo "[*] mode=${MODE} workers=${THREADS}  (streaming, no seed file)" >&2

PIDS=()
for idx in $(seq 0 $((THREADS - 1))); do
  log="${WORKDIR}/worker.${idx}.log"
  hits="${WORKDIR}/hits.${idx}.txt"
  echo "[*] Worker ${idx}: quality_seedgen --mode ${MODE} --shard ${idx}/${THREADS}" >&2
  python3 -u "${ROOT}/scripts/quality_seedgen.py" --mode "${MODE}" --shard "${idx}/${THREADS}" \
    | "${BRAINFLAYER}" -v -b "${BLOOM}" -m "${TABLE}" -j 1 \
      -o "${hits}" "$@" >"${log}" 2>&1 &
  PIDS+=($!)
done

STATUS=0
for pid in "${PIDS[@]}"; do
  if ! wait "${pid}"; then
    STATUS=1
  fi
done

if [[ "${STATUS}" -ne 0 ]]; then
  echo "[!] One or more workers failed:" >&2
  cat "${WORKDIR}"/worker.*.log >&2 || true
  exit 1
fi

if [[ -n "${OUTFILE}" ]]; then
  cat "${WORKDIR}"/hits.*.txt > "${OUTFILE}"
  echo "[+] Hits written to ${OUTFILE}" >&2
else
  cat "${WORKDIR}"/hits.*.txt
fi

echo "[*] Worker summaries:" >&2
for log in "${WORKDIR}"/worker.*.log; do
  echo "  $(basename "${log}"): $(tr '\r' '\n' < "${log}" | grep -E 'rate:|OpenMP|quality' | tail -1)" >&2
done
