#!/usr/bin/env bash
# Run one brainflayer process per CPU over a split seed file.
# Shared mmap of the bloom filter and ecmult table keeps RAM reasonable.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRAINFLAYER="${ROOT}/brainflayer"
ECMTABGEN="${ROOT}/ecmtabgen"
BLOOM="${ROOT}/data/btc.blf"
SEEDS="${ROOT}/data/seed_candidates.txt"
TABLE="${ROOT}/data/ecmult.w16.tab"
WINDOW=16
THREADS="${BF_PROCS:-$(nproc)}"
OUTFILE=""

usage() {
  echo "Usage: $0 [-b BLOOM] [-i SEEDS] [-j PROCS] [-o OUT] [-- extra brainflayer args]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -b) BLOOM="$2"; shift 2 ;;
    -i) SEEDS="$2"; shift 2 ;;
    -j) THREADS="$2"; shift 2 ;;
    -o) OUTFILE="$2"; shift 2 ;;
    --) shift; break ;;
    -h|--help) usage ;;
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
if [[ ! -f "${SEEDS}" ]]; then
  echo "Seed file not found: ${SEEDS}" >&2
  exit 1
fi
if [[ "${THREADS}" -lt 1 ]]; then
  echo "Invalid process count: ${THREADS}" >&2
  exit 1
fi

if [[ ! -f "${TABLE}" ]]; then
  if [[ ! -x "${ECMTABGEN}" ]]; then
    echo "ecmtabgen not found; run 'make' in ${ROOT}" >&2
    exit 1
  fi
  echo "[*] Building ecmult table ${TABLE} (window ${WINDOW})..." >&2
  "${ECMTABGEN}" "${WINDOW}" "${TABLE}"
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bf-run.XXXXXX")"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

echo "[*] Splitting $(basename "${SEEDS}") into ${THREADS} chunks..." >&2
split -n "l/${THREADS}" "${SEEDS}" "${WORKDIR}/part."

PIDS=()
PARTS=("${WORKDIR}"/part.*)
for idx in "${!PARTS[@]}"; do
  part="${PARTS[$idx]}"
  log="${WORKDIR}/worker.${idx}.log"
  hits="${WORKDIR}/hits.${idx}.txt"
  echo "[*] Worker ${idx}: $(basename "${part}")" >&2
  "${BRAINFLAYER}" -v -b "${BLOOM}" -i "${part}" -m "${TABLE}" -j 1 \
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

# Show last status line from each worker
echo "[*] Worker summaries:" >&2
for log in "${WORKDIR}"/worker.*.log; do
  echo "  $(basename "${log}"): $(tr '\r' '\n' < "${log}" | grep -E 'rate:|OpenMP' | tail -1)" >&2
done
