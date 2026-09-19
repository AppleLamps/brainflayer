#!/usr/bin/env bash
# Correctness checks for the threaded pubkey path.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BF="${ROOT}/brainflayer"
HEX2BLF="${ROOT}/hex2blf"
TABLE="${TABLE:-/tmp/ecmult.w16.tab}"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bf-verify.XXXXXX")"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

if [[ ! -x "${BF}" ]]; then
  echo "brainflayer binary not found; run 'make' in ${ROOT}" >&2
  exit 1
fi
if [[ ! -f "${TABLE}" ]]; then
  echo "ecmult table not found: ${TABLE}" >&2
  exit 1
fi

PHRASES="${WORKDIR}/phrases.txt"
printf 'password\ncorrect horse battery staple\nhello\nBrainflayer\n' > "${PHRASES}"
printf 'unrelated-candidate-%s\n' {1..200} >> "${PHRASES}"

echo "[*] generate-mode outputs match across worker counts"
"${BF}" -j 1 -c uc -i "${PHRASES}" -m "${TABLE}" -o "${WORKDIR}/gen1.txt"
"${BF}" -j 4 -c uc -i "${PHRASES}" -m "${TABLE}" -o "${WORKDIR}/gen4.txt"
"${BF}" -j 6 -c uc -i "${PHRASES}" -m "${TABLE}" -o "${WORKDIR}/gen6.txt"
sort "${WORKDIR}/gen1.txt" -o "${WORKDIR}/gen1.sorted"
sort "${WORKDIR}/gen4.txt" -o "${WORKDIR}/gen4.sorted"
sort "${WORKDIR}/gen6.txt" -o "${WORKDIR}/gen6.sorted"
diff -q "${WORKDIR}/gen1.sorted" "${WORKDIR}/gen4.sorted"
diff -q "${WORKDIR}/gen1.sorted" "${WORKDIR}/gen6.sorted"

echo "[*] incremental outputs match across worker counts"
"${BF}" -j 1 -c c -I 0000000000000000000000000000000000000000000000000000000000000001 \
  -N 64 -m "${TABLE}" -o "${WORKDIR}/incr1.txt"
"${BF}" -j 4 -c c -I 0000000000000000000000000000000000000000000000000000000000000001 \
  -N 64 -m "${TABLE}" -o "${WORKDIR}/incr4.txt"
sort "${WORKDIR}/incr1.txt" -o "${WORKDIR}/incr1.sorted"
sort "${WORKDIR}/incr4.txt" -o "${WORKDIR}/incr4.sorted"
diff -q "${WORKDIR}/incr1.sorted" "${WORKDIR}/incr4.sorted"

echo "[*] crack mode recovers planted phrases"
# The generate file is hash:type:algo:input; keep unique hash160s for the first 4 phrases.
cut -d: -f1 "${WORKDIR}/gen1.txt" | head -n 8 | sort -u > "${WORKDIR}/hashes.hex"
"${HEX2BLF}" "${WORKDIR}/hashes.hex" "${WORKDIR}/test.blf" >/dev/null
"${BF}" -j 4 -c uc -b "${WORKDIR}/test.blf" -i "${PHRASES}" -m "${TABLE}" -o "${WORKDIR}/hits.txt"
hits="$(wc -l < "${WORKDIR}/hits.txt")"
if [[ "${hits}" -lt 8 ]]; then
  echo "expected at least 8 hits, got ${hits}" >&2
  cat "${WORKDIR}/hits.txt" >&2
  exit 1
fi
grep -q ':password$' "${WORKDIR}/hits.txt"
grep -q ':hello$' "${WORKDIR}/hits.txt"
if grep -q 'unrelated-candidate' "${WORKDIR}/hits.txt"; then
  echo "false positive against empty extra candidates" >&2
  exit 1
fi

echo "[+] all optimization checks passed"
