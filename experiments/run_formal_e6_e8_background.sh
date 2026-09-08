#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DOCKER_DIR="$ROOT/apeq-docker/docker"
SCRIPTS="$ROOT/apeq-pipeline/scripts"
EXIT_FILE="$ROOT/formal-e6-e8-mixed.exit"

E6_RAW="$ROOT/formal-e6-batches-raw-mixed.csv"
E6_NORM="$ROOT/formal-e6-batches-normalized-mixed.csv"
E6_RUN_DIR="$ROOT/.runs-formal-e6-batches-mixed"
E6_EXPECTED=5760

E7_RAW="$ROOT/formal-e7-apeq-widths-raw-mixed.csv"
E7_NORM="$ROOT/formal-e7-apeq-widths-normalized-mixed.csv"
E7_RUN_DIR="$ROOT/.runs-formal-e7-apeq-widths-mixed"
E7_EXPECTED=1120

E8_RAW="$ROOT/formal-e8-rtt-extra-raw-mixed.csv"
E8_NORM="$ROOT/formal-e8-rtt-extra-normalized-mixed.csv"
E8_RUN_DIR="$ROOT/.runs-formal-e8-rtt-extra-mixed"
E8_EXPECTED=1920

row_count() {
  local file="$1" lines=0
  if [[ -f "$file" ]]; then
    lines=$(wc -l < "$file")
  fi
  if (( lines > 0 )); then
    printf '%s' "$((lines - 1))"
  else
    printf '0'
  fi
}

cd "$DOCKER_DIR" || exit 90
RESULTS="$E6_RAW" RUN_DIR="$E6_RUN_DIR" \
NETWORKS="lan wan" WIDTHS="8 16 24 32 48 64" \
BATCHES="200 400 800" REPS=10 TIMEOUT_S=300 \
bash ./run_all.sh
e6_run_rc=$?

cd "$ROOT" || exit 91
python3 "$SCRIPTS/normalize_aby_phases.py" "$E6_RAW" "$E6_NORM"
e6_normalize_rc=$?
e6_rows=$(row_count "$E6_NORM")
e6_p3_rc=1
e6_tables_rc=1
if (( e6_normalize_rc == 0 && e6_rows == E6_EXPECTED )); then
  python3 "$SCRIPTS/make_correctness.py" "$E6_NORM" \
    --out-prefix formal-e6-p3-correctness-mixed
  e6_p3_rc=$?
  python3 "$SCRIPTS/make_tables.py" "$E6_NORM" \
    --outdir formal-e6-tables-mixed
  e6_tables_rc=$?
fi

cd "$DOCKER_DIR" || exit 92
ONLY_PROTOCOLS=apeq RESULTS="$E7_RAW" RUN_DIR="$E7_RUN_DIR" \
NETWORKS="lan wan" WIDTHS="80 96" \
BATCHES="1 10 48 96 100 1000 10000" REPS=10 TIMEOUT_S=300 \
bash ./run_all.sh
e7_run_rc=$?

cd "$ROOT" || exit 93
python3 "$SCRIPTS/normalize_aby_phases.py" "$E7_RAW" "$E7_NORM"
e7_normalize_rc=$?
e7_rows=$(row_count "$E7_NORM")
e7_p3_rc=1
e7_tables_rc=1
if (( e7_normalize_rc == 0 && e7_rows == E7_EXPECTED )); then
  python3 "$SCRIPTS/make_correctness.py" "$E7_NORM" \
    --out-prefix formal-e7-p3-correctness-mixed
  e7_p3_rc=$?
  python3 "$SCRIPTS/make_tables.py" "$E7_NORM" \
    --outdir formal-e7-tables-mixed
  e7_tables_rc=$?
fi

cd "$DOCKER_DIR" || exit 94
RESULTS="$E8_RAW" RUN_DIR="$E8_RUN_DIR" \
NETWORKS="rtt10 rtt60" WIDTHS="8 16 24 32 48 64" \
BATCHES=100 REPS=10 TIMEOUT_S=300 \
bash ./run_all.sh
e8_run_rc=$?

cd "$ROOT" || exit 95
python3 "$SCRIPTS/normalize_aby_phases.py" "$E8_RAW" "$E8_NORM"
e8_normalize_rc=$?
e8_rows=$(row_count "$E8_NORM")

final_rc=0
if (( e6_normalize_rc != 0 || e6_rows != E6_EXPECTED ||
      e6_p3_rc != 0 || e6_tables_rc != 0 ||
      e7_normalize_rc != 0 || e7_rows != E7_EXPECTED ||
      e7_p3_rc != 0 || e7_tables_rc != 0 ||
      e8_normalize_rc != 0 || e8_rows != E8_EXPECTED )); then
  final_rc=1
fi

{
  printf 'final_rc=%s\n' "$final_rc"
  printf 'e6_run_rc=%s\n' "$e6_run_rc"
  printf 'e6_normalize_rc=%s\n' "$e6_normalize_rc"
  printf 'e6_p3_rc=%s\n' "$e6_p3_rc"
  printf 'e6_tables_rc=%s\n' "$e6_tables_rc"
  printf 'e6_rows=%s\n' "$e6_rows"
  printf 'e6_expected_rows=%s\n' "$E6_EXPECTED"
  printf 'e7_run_rc=%s\n' "$e7_run_rc"
  printf 'e7_normalize_rc=%s\n' "$e7_normalize_rc"
  printf 'e7_p3_rc=%s\n' "$e7_p3_rc"
  printf 'e7_tables_rc=%s\n' "$e7_tables_rc"
  printf 'e7_rows=%s\n' "$e7_rows"
  printf 'e7_expected_rows=%s\n' "$E7_EXPECTED"
  printf 'e8_run_rc=%s\n' "$e8_run_rc"
  printf 'e8_normalize_rc=%s\n' "$e8_normalize_rc"
  printf 'e8_rows=%s\n' "$e8_rows"
  printf 'e8_expected_rows=%s\n' "$E8_EXPECTED"
  printf 'finished_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$EXIT_FILE"

exit "$final_rc"
