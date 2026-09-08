#!/usr/bin/env bash
# Reproduce the focused TDSC OLE-parameter sweep after Docker Desktop is healthy.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="${OUT_DIR:-$PROJECT_ROOT/reproduction/experiments/ole-parameter-sweep}"

mkdir -p "$OUT_DIR"

"$SCRIPT_DIR/build_image.sh" apeq
"$SCRIPT_DIR/build_image.sh" apeq-vole
"$SCRIPT_DIR/build_image.sh" emp
"$SCRIPT_DIR/build_image.sh" lu

run_matrix() {
  local name="$1" protocols="$2" variants="$3"
  shift 3
  RESULTS="$OUT_DIR/$name.csv" \
  RUN_DIR="$OUT_DIR/party-runs-$name" \
  ONLY_PROTOCOLS="$protocols" \
  ONLY_VARIANTS="$variants" \
  WIDTHS="64" \
  BATCHES="32 48 100 400" \
  NETWORKS="lan wan" \
  REPS="10" \
  "$@" "$SCRIPT_DIR/run_all.sh"
}

# Each OLE configuration gets a separate results file so interrupted runs can
# resume without the harness mistaking a different configuration for a match.
run_matrix "ole-current" "apeq" "ole" \
  env OLE_N=1024 OLE_RHO=769 OLE_ELL=255 OLE_K=128 OLE_T=48
run_matrix "ole-smaller-group" "apeq" "ole" \
  env OLE_N=1024 OLE_RHO=769 OLE_ELL=255 OLE_K=128 OLE_T=32
run_matrix "ole-longer-code" "apeq" "ole" \
  env OLE_N=1280 OLE_RHO=1025 OLE_ELL=255 OLE_K=128 OLE_T=48

# Direct controls are measured once on the same host and network profiles.
run_matrix "controls-emp-lu" "emp_eq lu_eq" "" env
run_matrix "control-apeq-vole" "apeq" "vole_hash" env

echo "TDSC E2 sweep complete: $OUT_DIR"
