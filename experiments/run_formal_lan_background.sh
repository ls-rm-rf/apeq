#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT/apeq-docker/docker"
RAW="$ROOT/formal-lan-76a3.csv"
NORMALIZED="$ROOT/formal-lan-normalized-76a3.csv"
RUN_DIR="$ROOT/.runs-formal-lan-76a3"
EXIT_FILE="$ROOT/formal-lan-76a3.exit"
EXPECTED_ROWS=6720

cd "$DOCKER_DIR" || exit 90
RESULTS="$RAW" \
RUN_DIR="$RUN_DIR" \
NETWORKS=lan \
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

p3_rc=1
tables_rc=1
if (( normalize_rc == 0 && data_rows == EXPECTED_ROWS )); then
  python3 apeq-pipeline/scripts/make_correctness.py \
    "$NORMALIZED" --out-prefix formal-lan-p3-correctness-76a3
  p3_rc=$?
  python3 apeq-pipeline/scripts/make_tables.py \
    "$NORMALIZED" --outdir formal-lan-tables-76a3
  tables_rc=$?
fi

final_rc=0
if (( normalize_rc != 0 || data_rows != EXPECTED_ROWS ||
      p3_rc != 0 || tables_rc != 0 )); then
  final_rc=1
fi

{
  printf 'final_rc=%s\n' "$final_rc"
  printf 'run_all_rc=%s\n' "$run_all_rc"
  printf 'normalize_rc=%s\n' "$normalize_rc"
  printf 'p3_rc=%s\n' "$p3_rc"
  printf 'tables_rc=%s\n' "$tables_rc"
  printf 'data_rows=%s\n' "$data_rows"
  printf 'expected_rows=%s\n' "$EXPECTED_ROWS"
  printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EXIT_FILE"

exit "$final_rc"
