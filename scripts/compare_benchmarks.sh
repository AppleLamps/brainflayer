#!/usr/bin/env bash
set -euo pipefail

before="${1:?usage: compare_benchmarks.sh BEFORE AFTER}"
after="${2:?usage: compare_benchmarks.sh BEFORE AFTER}"

echo "case                    before      after       change"
echo "----------------------  ----------  ----------  --------"

while IFS= read -r line; do
  [[ "${line}" =~ ^# ]] && continue
  [[ -z "${line}" ]] && continue
  name="${line%%$'\t'*}"
  bval="${line#*$'\t'}"
  aval="$(grep -F "${name}"$'\t' "${after}" | cut -f2 || true)"
  if [[ -z "${aval}" ]]; then
    printf '%-22s  %10s  %10s  %s\n' "${name}" "${bval}" "—" "missing"
    continue
  fi
  python3 - <<PY
b=float("${bval}"); a=float("${aval}")
pct=(a-b)/b*100 if b else 0
sign="+" if pct>=0 else ""
print(f"{'${name}':<22}  {b:10.2f}  {a:10.2f}  {sign}{pct:.1f}%")
PY
done < "${before}"
