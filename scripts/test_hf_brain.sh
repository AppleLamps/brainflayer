#!/usr/bin/env bash
# Exercise brainflayer / blfchk against data/keys.blf (AppleLampsX/brain).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BF="${ROOT}/brainflayer"
BLFCHK="${ROOT}/blfchk"
TABLE="${TABLE:-/tmp/ecmult.w16.tab}"
BLF="${BLF:-${ROOT}/data/keys.blf}"
BLOOM_SIZE=$((512 * 1024 * 1024))
WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/bf-hf.XXXXXX")"
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
if [[ ! -f "${BLF}" ]]; then
  echo "missing ${BLF}; run scripts/fetch_hf_brain.sh" >&2
  exit 1
fi

sz="$(stat -c%s "${BLF}")"
if [[ "${sz}" -ne "${BLOOM_SIZE}" ]]; then
  echo "unexpected bloom size ${sz} (expected ${BLOOM_SIZE})" >&2
  exit 1
fi

echo "[*] ${BLF} size ok (${sz} bytes)"

python3 - <<PY
import os
path = "${BLF}"
sz = os.path.getsize(path)
chunks = []
with open(path, "rb") as f:
    for off in (0, sz // 2, max(0, sz - 16 * 1024 * 1024)):
        f.seek(off)
        chunks.append(f.read(16 * 1024 * 1024))
bits = sum(bin(b).count("1") for c in chunks for b in c)
total = sum(len(c) * 8 for c in chunks)
density = bits / total
print(f"[*] sampled bit density {density:.4f}")
# 20 hashes, m=2^32 => n ≈ -ln(1-p)*m/k
import math
n = -math.log(1.0 - density) * (1 << 32) / 20.0
print(f"[*] implied membership ~{n/1e6:.1f} million hash160s")
if density < 0.05 or density > 0.9:
    raise SystemExit(f"implausible bloom density {density}")
PY

echo "[*] negative control: 5000 synthetic phrases must not hit"
python3 - <<'PY' > "${WORKDIR}/neg.txt"
for i in range(5000):
    print(f"bf-selftest-neg-{i:05d}-not-a-real-brainwallet")
PY
"${BF}" -j 4 -c uc -b "${BLF}" -i "${WORKDIR}/neg.txt" -m "${TABLE}" -o "${WORKDIR}/neg.hits"
if [[ -s "${WORKDIR}/neg.hits" ]]; then
  echo "unexpected bloom hits on synthetic phrases:" >&2
  cat "${WORKDIR}/neg.hits" >&2
  exit 1
fi

echo "[*] generated hash160s from those phrases must also miss via blfchk"
"${BF}" -j 4 -c uc -N 256 -i "${WORKDIR}/neg.txt" -m "${TABLE}" -o "${WORKDIR}/gen.txt"
cut -d: -f1 "${WORKDIR}/gen.txt" | sort -u > "${WORKDIR}/gen.hex"
"${BLFCHK}" "${BLF}" < "${WORKDIR}/gen.hex" > "${WORKDIR}/blfchk.hits"
if [[ -s "${WORKDIR}/blfchk.hits" ]]; then
  echo "blfchk false positives on synthetic hash160s:" >&2
  cat "${WORKDIR}/blfchk.hits" >&2
  exit 1
fi

echo "[*] 20k-phrase crack throughput"
python3 - <<'PY' > "${WORKDIR}/bench.txt"
for i in range(20000):
    print(f"hf-brain-bench-{i:05d}")
PY
"${BF}" -v -j 4 -c uc -N 20000 -b "${BLF}" -i "${WORKDIR}/bench.txt" -m "${TABLE}" -o "${WORKDIR}/bench.hits"
if [[ -s "${WORKDIR}/bench.hits" ]]; then
  echo "unexpected hits during throughput run:" >&2
  cat "${WORKDIR}/bench.hits" >&2
  exit 1
fi

H160="${H160:-${ROOT}/data/h160.bin}"
if [[ -f "${H160}" ]]; then
  echo "[*] exact hash160 file present; verify -f rejects bloom false positives"
  python3 "${ROOT}/scripts/h160_lookup.py" "${H160}" \
    0000000000000000000000000000000000000000 \
    ffffffffffffffffffffffffffffffffffffffff
  if python3 "${ROOT}/scripts/h160_lookup.py" "${H160}" \
      5d3a136dda11e1616e72416e7c9d7581863aecdf; then
    echo "unexpected: bloom-FP hash160 is in ${H160}" >&2
    exit 1
  fi
  printf 'custom hardship\n' > "${WORKDIR}/fp.txt"
  "${BF}" -j 1 -c uc -b "${BLF}" -i "${WORKDIR}/fp.txt" -m "${TABLE}" -o "${WORKDIR}/fp-bloom.hits"
  if [[ ! -s "${WORKDIR}/fp-bloom.hits" ]]; then
    echo "expected bloom hit for custom hardship (false positive probe)" >&2
    exit 1
  fi
  "${BF}" -j 1 -c uc -b "${BLF}" -f "${H160}" -i "${WORKDIR}/fp.txt" -m "${TABLE}" -o "${WORKDIR}/fp-exact.hits"
  if [[ -s "${WORKDIR}/fp-exact.hits" ]]; then
    echo "-f did not suppress bloom false positive:" >&2
    cat "${WORKDIR}/fp-exact.hits" >&2
    exit 1
  fi
  echo "[+] -f against AppleLampsX/h160 suppressed the bloom false positive"
fi

echo "[+] AppleLampsX/brain bloom checks passed"
