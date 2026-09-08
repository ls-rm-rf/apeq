#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
LOG="$ROOT/reproduction/experiments/r2-build-$1.log"
if [[ "$1" == ole ]]; then
  bash apeq-docker/docker/build_image.sh ips-ole-libote > "$LOG" 2>&1
  bash apeq-docker/docker/build_image.sh apeq >> "$LOG" 2>&1
else
  bash apeq-docker/docker/build_image.sh aby > "$LOG" 2>&1
fi
