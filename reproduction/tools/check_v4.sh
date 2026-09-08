#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/reproduction/experiments/implementation-v4"
docker run --rm -v "$ROOT:/work" --entrypoint bash apeq/apeq-vole -c '
  cp /work/analysis/check_vole_session.cpp /opt/apeq-vole-bench/apeq_vole_eq.cpp
  cd /opt/apeq-vole-bench
  make -j4
  ./driver
' > "$OUT/session-tests.log" 2>&1
docker run --rm apeq/ips-ole-libote > "$OUT/core-tests.log" 2>&1
