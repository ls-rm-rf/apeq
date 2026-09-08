#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT/apeq-docker/docker"
RAW="$ROOT/formal-round-widths-raw-8251.csv"
NORMALIZED="$ROOT/formal-round-widths-normalized-8251.csv"
RUN_DIR="$ROOT/.runs-formal-round-widths-8251"
EXIT_FILE="$ROOT/formal-round-widths-8251.exit"
EXPECTED_ROWS=3840

cd "$DOCKER_DIR" || exit 90
RESULTS="$RAW" \
RUN_DIR="$RUN_DIR" \
NETWORKS="rtt0p5 rtt20 rtt40 rtt80" \
WIDTHS="8 16 24 32 48 64" \
BATCHES=100 \
REPS=10 \
TIMEOUT_S=300 \
bash ./run_all.sh
run_all_rc=$?

cd "$ROOT" || exit 91
python3 apeq-pipeline/scripts/normalize_aby_phases.py \
  "$RAW" "$NORMALIZED"
normalize_rc=$?

data_rows=0
if [[ -f "$NORMALIZED" ]]; then
  line_count=$(wc -l < "$NORMALIZED")
  if (( line_count > 0 )); then
    data_rows=$((line_count - 1))
  fi
fi

estimate_rc=1
if (( normalize_rc == 0 && data_rows == EXPECTED_ROWS )); then
  python3 apeq-pipeline/scripts/estimate_rounds.py \
    "$NORMALIZED" --out-prefix formal-round-width-estimates-8251
  estimate_rc=$?
fi

final_rc=0
# The raw validator can reject ABY asynchronous receive-phase attribution.
# Completion is therefore determined by the normalized validator, exact row
# count, and successful estimate generation; run_all_rc remains in the marker
# as provenance and is not silently discarded.
if (( normalize_rc != 0 || data_rows != EXPECTED_ROWS || estimate_rc != 0 )); then
  final_rc=1
fi

{
  printf 'final_rc=%s\n' "$final_rc"
  printf 'run_all_rc=%s\n' "$run_all_rc"
  printf 'normalize_rc=%s\n' "$normalize_rc"
  printf 'estimate_rc=%s\n' "$estimate_rc"
  printf 'data_rows=%s\n' "$data_rows"
  printf 'expected_rows=%s\n' "$EXPECTED_ROWS"
  printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EXIT_FILE"

exit "$final_rc"
