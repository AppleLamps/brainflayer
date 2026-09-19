#!/usr/bin/env bash
# Throughput benchmarks for brainflayer (parse final rate from -v stderr).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BF="${ROOT}/brainflayer"
HEX2BLF="${ROOT}/hex2blf"
TABLE="${TABLE:-/tmp/ecmult.w16.tab}"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bf-bench.XXXXXX")"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

if [[ ! -x "${BF}" ]]; then
  echo "Run 'make' in ${ROOT} first" >&2
  exit 1
fi
if [[ ! -f "${TABLE}" ]]; then
  echo "Missing ecmult table: ${TABLE}" >&2
  exit 1
fi

PHRASES="${WORKDIR}/phrases.txt"
python3 - <<'PY' > "${PHRASES}"
for i in range(50000):
    print(f"benchmark-phrase-{i:05d}")
PY

rate_from_run() {
  # Last verbose rate line (overall average on final batch).
  "$@" -o /dev/null 2>&1 | tee "${WORKDIR}/run.log" \
    | grep -E 'rate:' | tail -1 \
    | sed -E 's/.*rate:[[:space:]]*([0-9.]+).*/\1/'
}

run_case() {
  local name="$1"
  shift
  local r
  r="$(rate_from_run "$@")"
  printf '%s\t%s\n' "${name}" "${r}"
}

echo "[*] benchmark workdir ${WORKDIR}"
RESULTS="${1:-/dev/stdout}"

{
  echo "# brainflayer benchmark $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# TABLE=${TABLE} BF=${BF}"
  run_case "generate_stdin_j1" \
    "${BF}" -v -j 1 -c uc -N 50000 -m "${TABLE}" < "${PHRASES}"
  run_case "generate_stdin_j4" \
    "${BF}" -v -j 4 -c uc -N 50000 -m "${TABLE}" < "${PHRASES}"
  run_case "generate_file_j4" \
    "${BF}" -v -j 4 -c uc -N 50000 -i "${PHRASES}" -m "${TABLE}"
  run_case "generate_compressed_j4" \
    "${BF}" -v -j 4 -c c -N 50000 -i "${PHRASES}" -m "${TABLE}"
  run_case "incremental_j4" \
    "${BF}" -v -j 4 -c uc -I 0000000000000000000000000000000000000000000000000000000000000001 \
    -N 20000 -m "${TABLE}"

  # Crack path with -f verification (all candidates in bloom + sorted bin).
  "${BF}" -v -j 1 -c uc -N 5000 -i "${PHRASES}" -m "${TABLE}" -o "${WORKDIR}/gen5k.txt" 2>/dev/null
  cut -d: -f1 "${WORKDIR}/gen5k.txt" | sort -u > "${WORKDIR}/hashes.hex"
  "${HEX2BLF}" "${WORKDIR}/hashes.hex" "${WORKDIR}/test.blf" >/dev/null
  python3 - <<PY
import pathlib
hexes = sorted(set(pathlib.Path("${WORKDIR}/hashes.hex").read_text().split()))
pathlib.Path("${WORKDIR}/hashes.bin").write_bytes(b"".join(bytes.fromhex(h) for h in hexes if h))
PY
  run_case "crack_verify_f_j4" \
    "${BF}" -v -j 4 -c uc -N 5000 -i "${PHRASES}" -m "${TABLE}" \
    -b "${WORKDIR}/test.blf" -f "${WORKDIR}/hashes.bin"
} | tee "${RESULTS}"
