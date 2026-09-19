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

echo "[*] -k/-N with multiple workers starts at the first unskipped line"
printf 'skip-me\nkeep-me\nignore-a\nignore-b\nignore-c\n' > "${WORKDIR}/skip.txt"
"${BF}" -j 4 -k 1 -N 1 -c c -i "${WORKDIR}/skip.txt" -m "${TABLE}" -o "${WORKDIR}/skip.out"
if ! grep -q ':keep-me$' "${WORKDIR}/skip.out"; then
  echo "expected keep-me after -k 1 -N 1, got:" >&2
  cat "${WORKDIR}/skip.out" >&2
  exit 1
fi
if grep -qE 'skip-me|ignore-' "${WORKDIR}/skip.out"; then
  echo "processed the wrong line for -k 1 -N 1 -j 4" >&2
  cat "${WORKDIR}/skip.out" >&2
  exit 1
fi

echo "[*] crack mode recovers planted phrases"
# The generate file is hash:type:algo:input; keep unique hash160s for the first 4 phrases.
head -n 8 "${WORKDIR}/gen1.txt" | cut -d: -f1 | sort -u > "${WORKDIR}/hashes.hex"
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
