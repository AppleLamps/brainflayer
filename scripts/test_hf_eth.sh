#!/usr/bin/env bash
# Exercise brainflayer against data/eth.blf + data/eth.bin (AppleLampsX/eth).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BF="${ROOT}/brainflayer"
BLFCHK="${ROOT}/blfchk"
TABLE="${TABLE:-/tmp/ecmult.w16.tab}"
BLF="${BLF:-${ROOT}/data/eth.blf}"
BIN="${BIN:-${ROOT}/data/eth.bin}"
BLOOM_SIZE=$((512 * 1024 * 1024))
# First line of AppleLampsX/eth (WETH); used only as a conversion sanity check.
WETH="c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bf-eth.XXXXXX")"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

if [[ ! -x "${BF}" || ! -x "${BLFCHK}" ]]; then
  echo "build binaries first: make -C ${ROOT}" >&2
  exit 1
fi
if [[ ! -f "${TABLE}" ]]; then
  echo "ecmult table not found: ${TABLE}" >&2
  exit 1
fi
if [[ ! -f "${BLF}" || ! -f "${BIN}" ]]; then
  echo "missing ${BLF} or ${BIN}; run scripts/fetch_hf_eth.sh" >&2
  exit 1
fi

sz="$(stat -c%s "${BLF}")"
if [[ "${sz}" -ne "${BLOOM_SIZE}" ]]; then
  echo "unexpected bloom size ${sz} (expected ${BLOOM_SIZE})" >&2
  exit 1
fi
binsz="$(stat -c%s "${BIN}")"
if [[ $((binsz % 20)) -ne 0 ]]; then
  echo "unexpected ${BIN} size ${binsz}" >&2
  exit 1
fi
echo "[*] ${BLF} and ${BIN} ($((binsz / 20)) addresses) ok"

echo "[*] WETH must be in the exact list and bloom (conversion check)"
python3 "${ROOT}/scripts/h160_lookup.py" "${BIN}" "${WETH}"
printf '%s\n' "${WETH}" | "${BLFCHK}" "${BLF}" > "${WORKDIR}/weth.bloom"
if [[ ! -s "${WORKDIR}/weth.bloom" ]]; then
  echo "WETH missing from ${BLF}" >&2
  exit 1
fi
if python3 "${ROOT}/scripts/h160_lookup.py" "${BIN}" \
    ffffffffffffffffffffffffffffffffffffffff; then
  echo "unexpected: all-0xff address is in ${BIN}" >&2
  exit 1
fi

echo "[*] negative control: 2000 synthetic phrases must not hit with -f"
python3 - <<'PY' > "${WORKDIR}/neg.txt"
for i in range(2000):
    print(f"bf-eth-selftest-neg-{i:05d}-not-a-real-brainwallet")
PY
"${BF}" -j 4 -c e -b "${BLF}" -f "${BIN}" -i "${WORKDIR}/neg.txt" -m "${TABLE}" -o "${WORKDIR}/neg.hits"
if [[ -s "${WORKDIR}/neg.hits" ]]; then
  echo "unexpected eth hits on synthetic phrases:" >&2
  cat "${WORKDIR}/neg.hits" >&2
  exit 1
fi

echo "[+] AppleLampsX/eth checks passed"
