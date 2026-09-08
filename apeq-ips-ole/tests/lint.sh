#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if grep -RInE 'bernoulli_distribution|rand\(\)[[:space:]]*%' "$ROOT/src"; then
  echo "forbidden biased noise sampler found" >&2
  exit 1
fi

if grep -RInE 'uint(64|128)_t[^;]*(field|Fp)[^;]*[+*-]' "$ROOT/src"; then
  echo "raw integer arithmetic on a field-carrying value found" >&2
  exit 1
fi

echo "IPS-OLE source lint passed"

