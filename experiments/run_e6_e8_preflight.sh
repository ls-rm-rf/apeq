#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT/apeq-docker/docker"
SCRIPTS="$ROOT/apeq-pipeline/scripts"

MAIN_RAW="$ROOT/e6e8-preflight-main-raw.csv"
MAIN_NORM="$ROOT/e6e8-preflight-main-normalized.csv"
WIDE_RAW="$ROOT/e6e8-preflight-wide-raw.csv"
WIDE_NORM="$ROOT/e6e8-preflight-wide-normalized.csv"

cd "$DOCKER_DIR" || exit 90
RESULTS="$MAIN_RAW" RUN_DIR="$ROOT/.runs-e6e8-preflight-main" \
NETWORKS=rtt10 WIDTHS=8 BATCHES=200 REPS=1 TIMEOUT_S=300 \
bash ./run_all.sh
main_run_rc=$?

cd "$ROOT" || exit 91
python3 "$SCRIPTS/normalize_aby_phases.py" "$MAIN_RAW" "$MAIN_NORM"
main_normalize_rc=$?
main_rows=$(($(wc -l < "$MAIN_NORM") - 1))

cd "$DOCKER_DIR" || exit 92
ONLY_PROTOCOLS=apeq RESULTS="$WIDE_RAW" RUN_DIR="$ROOT/.runs-e6e8-preflight-wide" \
NETWORKS=lan WIDTHS=80 BATCHES=1 REPS=1 TIMEOUT_S=300 \
bash ./run_all.sh
wide_run_rc=$?

cd "$ROOT" || exit 93
python3 "$SCRIPTS/normalize_aby_phases.py" "$WIDE_RAW" "$WIDE_NORM"
wide_normalize_rc=$?
wide_rows=$(($(wc -l < "$WIDE_NORM") - 1))

printf 'main_run_rc=%s main_normalize_rc=%s main_rows=%s\n' \
  "$main_run_rc" "$main_normalize_rc" "$main_rows"
printf 'wide_run_rc=%s wide_normalize_rc=%s wide_rows=%s\n' \
  "$wide_run_rc" "$wide_normalize_rc" "$wide_rows"

if (( main_normalize_rc != 0 || main_rows != 16 ||
      wide_normalize_rc != 0 || wide_rows != 4 )); then
  exit 1
fi
