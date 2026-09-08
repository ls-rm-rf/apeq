#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT/apeq-docker/docker"
RAW="$ROOT/formal-apeq-wide-8251.csv"
NORMALIZED="$ROOT/formal-apeq-wide-normalized-8251.csv"
RUN_DIR="$ROOT/.runs-formal-apeq-wide-8251"
EXIT_FILE="$ROOT/formal-apeq-wide-8251.exit"
EXPECTED_ROWS=1120

cd "$DOCKER_DIR" || exit 90
RESULTS="$RAW" \
RUN_DIR="$RUN_DIR" \
ONLY_PROTOCOLS=apeq \
WIDTHS="120 126" \
NETWORKS="lan wan" \
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
    "$NORMALIZED" --out-prefix formal-apeq-wide-p3-correctness-8251
  p3_rc=$?
  python3 apeq-pipeline/scripts/make_tables.py \
    "$NORMALIZED" --outdir formal-apeq-wide-tables-8251
  tables_rc=$?
fi

final_rc=0
if (( run_all_rc != 0 || normalize_rc != 0 || data_rows != EXPECTED_ROWS ||
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
