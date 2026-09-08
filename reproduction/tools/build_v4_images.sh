#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$ROOT/reproduction/experiments/implementation-v4"
mkdir -p "$OUT"
cd "$ROOT"
for target in ips-ole-libote apeq apeq-ot apeq-vole aby; do
  echo "Building $target"
  bash apeq-docker/docker/build_image.sh "$target" > "$OUT/build-$target.log" 2>&1
done
docker image inspect apeq/apeq apeq/apeq-ot apeq/apeq-vole apeq/aby > "$OUT/image-inspect.json"
