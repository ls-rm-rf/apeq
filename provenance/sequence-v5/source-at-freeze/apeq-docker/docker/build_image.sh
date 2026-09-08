#!/usr/bin/env bash
# Build one benchmark image with a shared content-derived source revision.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
TARGET="${1:-}"

case "$TARGET" in
  mock)       IMAGE="apeq/mock";       DOCKERFILE="Dockerfile.mock" ;;
  emp)        IMAGE="apeq/emp";        DOCKERFILE="Dockerfile.emp" ;;
  aby)        IMAGE="apeq/aby";        DOCKERFILE="Dockerfile.aby" ;;
  cryptflow2) IMAGE="apeq/cryptflow2"; DOCKERFILE="Dockerfile.cryptflow2" ;;
  volepsi)    IMAGE="apeq/volepsi";    DOCKERFILE="Dockerfile.volepsi" ;;
  apeq)       IMAGE="apeq/apeq";       DOCKERFILE="Dockerfile.apeq" ;;
  apeq-ot)    IMAGE="apeq/apeq-ot";    DOCKERFILE="Dockerfile.apeq-ot" ;;
  apeq-vole)  IMAGE="apeq/apeq-vole";  DOCKERFILE="Dockerfile.apeq-vole" ;;
  lu)         IMAGE="apeq/lu";         DOCKERFILE="Dockerfile.lu" ;;
  ips-ole-core) IMAGE="apeq/ips-ole-core"; DOCKERFILE="Dockerfile" ;;
  ips-ole-libote) IMAGE="apeq/ips-ole-libote"; DOCKERFILE="Dockerfile.libote" ;;
  *)
    echo "usage: $0 {mock|emp|aby|cryptflow2|volepsi|apeq|apeq-ot|apeq-vole|lu|ips-ole-core|ips-ole-libote}" >&2
    exit 2
    ;;
esac

for cmd in docker find sort xargs sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "missing command: $cmd" >&2; exit 2; }
done

if [[ "$TARGET" == "lu" && ! -d "$PROJECT_ROOT/apeq-lu-eq/2PC_eq_cmp-main" ]]; then
  echo "Lu et al. source is not bundled because the upstream archive has no license." >&2
  echo "Follow apeq-lu-eq/SOURCE.md and extract it as apeq-lu-eq/2PC_eq_cmp-main/." >&2
  exit 2
fi

digest="$(
  cd "$PROJECT_ROOT"
  {
    find apeq-docker/docker/bench apeq-docker/docker/patches \
         apeq-pipeline/spec -type f -print0
    find apeq-pipeline/scripts -maxdepth 1 -type f -name '*.py' -print0
    find apeq-ips-ole -type f -print0
    find apeq-lu-eq -maxdepth 1 -type f -print0
    if [[ -d apeq-lu-eq/2PC_eq_cmp-main ]]; then
      find apeq-lu-eq/2PC_eq_cmp-main -type f -print0
    fi
    printf '%s\0' apeq-docker/docker/Dockerfile.* \
      apeq-docker/docker/build_image.sh \
      apeq-docker/docker/run_all.sh \
      apeq-docker/docker/run_pair.ps1 \
      apeq-docker/docker/write_status_rows.py
  } | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-12
)"
revision="tree-$digest"

echo "building $IMAGE from source revision $revision"
if [[ "$TARGET" == "ips-ole-core" || "$TARGET" == "ips-ole-libote" ]]; then
  cd "$PROJECT_ROOT/apeq-ips-ole"
  docker build --progress=plain --build-arg "IPS_OLE_REVISION=$revision" \
    -t "$IMAGE" -f "$DOCKERFILE" .
elif [[ "$TARGET" == "lu" ]]; then
  cd "$SCRIPT_DIR"
  docker build --progress=plain --build-arg "BENCH_REVISION=$revision" \
    --build-context "lu-source=$PROJECT_ROOT/apeq-lu-eq/2PC_eq_cmp-main" \
    -t "$IMAGE" -f "$DOCKERFILE" .
else
  cd "$SCRIPT_DIR"
  docker build --progress=plain --build-arg "BENCH_REVISION=$revision" \
    -t "$IMAGE" -f "$DOCKERFILE" .
fi
echo "$IMAGE revision=$revision"
