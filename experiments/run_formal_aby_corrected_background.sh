#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT/apeq-docker/docker"
ROUND_RAW="$ROOT/formal-aby-round-widths-raw-b117.csv"
ROUND_NORM="$ROOT/formal-aby-round-widths-normalized-b117.csv"
ROUND_DIR="$ROOT/.runs-formal-aby-round-widths-b117"
MAIN_RAW="$ROOT/formal-aby-main-raw-b117.csv"
MAIN_NORM="$ROOT/formal-aby-main-normalized-b117.csv"
MAIN_DIR="$ROOT/.runs-formal-aby-main-b117"
EXIT_FILE="$ROOT/formal-aby-corrected-b117.exit"
EXPECTED_ROUND_ROWS=960
EXPECTED_MAIN_ROWS=3360

cd "$DOCKER_DIR" || exit 90
ONLY_PROTOCOLS=aby_eq \
RESULTS="$ROUND_RAW" RUN_DIR="$ROUND_DIR" \
NETWORKS="rtt0p5 rtt20 rtt40 rtt80" \
WIDTHS="8 16 24 32 48 64" BATCHES=100 REPS=10 TIMEOUT_S=300 \
bash ./run_all.sh
round_run_rc=$?

cd "$ROOT" || exit 91
python3 apeq-pipeline/scripts/normalize_aby_phases.py \
  "$ROUND_RAW" "$ROUND_NORM"
round_normalize_rc=$?
round_rows=0
if [[ -f "$ROUND_NORM" ]]; then
  round_lines=$(wc -l < "$ROUND_NORM")
  (( round_lines > 0 )) && round_rows=$((round_lines - 1))
fi
round_estimate_rc=1
if (( round_normalize_rc == 0 && round_rows == EXPECTED_ROUND_ROWS )); then
  python3 apeq-pipeline/scripts/estimate_rounds.py "$ROUND_NORM" \
    --out-prefix formal-aby-round-width-estimates-b117
  round_estimate_rc=$?
fi

cd "$DOCKER_DIR" || exit 92
ONLY_PROTOCOLS=aby_eq \
RESULTS="$MAIN_RAW" RUN_DIR="$MAIN_DIR" \
NETWORKS="lan wan" WIDTHS="8 16 24 32 48 64" \
BATCHES="1 10 48 96 100 1000 10000" REPS=10 TIMEOUT_S=300 \
bash ./run_all.sh
main_run_rc=$?

cd "$ROOT" || exit 93
python3 apeq-pipeline/scripts/normalize_aby_phases.py \
  "$MAIN_RAW" "$MAIN_NORM"
main_normalize_rc=$?
main_rows=0
if [[ -f "$MAIN_NORM" ]]; then
  main_lines=$(wc -l < "$MAIN_NORM")
  (( main_lines > 0 )) && main_rows=$((main_lines - 1))
fi
main_p3_rc=1
main_tables_rc=1
if (( main_normalize_rc == 0 && main_rows == EXPECTED_MAIN_ROWS )); then
  python3 apeq-pipeline/scripts/make_correctness.py "$MAIN_NORM" \
    --out-prefix formal-aby-main-p3-correctness-b117
  main_p3_rc=$?
  python3 apeq-pipeline/scripts/make_tables.py "$MAIN_NORM" \
    --outdir formal-aby-main-tables-b117
  main_tables_rc=$?
fi

final_rc=0
if (( round_normalize_rc != 0 || round_rows != EXPECTED_ROUND_ROWS ||
      round_estimate_rc != 0 || main_normalize_rc != 0 ||
      main_rows != EXPECTED_MAIN_ROWS || main_p3_rc != 0 ||
      main_tables_rc != 0 )); then
  final_rc=1
fi

{
  printf 'final_rc=%s\n' "$final_rc"
  printf 'round_run_rc=%s\n' "$round_run_rc"
  printf 'round_normalize_rc=%s\n' "$round_normalize_rc"
  printf 'round_estimate_rc=%s\n' "$round_estimate_rc"
  printf 'round_rows=%s\n' "$round_rows"
  printf 'expected_round_rows=%s\n' "$EXPECTED_ROUND_ROWS"
  printf 'main_run_rc=%s\n' "$main_run_rc"
  printf 'main_normalize_rc=%s\n' "$main_normalize_rc"
  printf 'main_p3_rc=%s\n' "$main_p3_rc"
  printf 'main_tables_rc=%s\n' "$main_tables_rc"
  printf 'main_rows=%s\n' "$main_rows"
  printf 'expected_main_rows=%s\n' "$EXPECTED_MAIN_ROWS"
  printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EXIT_FILE"

exit "$final_rc"
