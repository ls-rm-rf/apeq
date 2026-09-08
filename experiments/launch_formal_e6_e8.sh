#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$ROOT/.formal-e6-e8-mixed.pid"
LOG_FILE="$ROOT/formal-e6-e8-mixed.log"
ERR_FILE="$ROOT/formal-e6-e8-mixed.err.log"

if [[ -f "$PID_FILE" ]]; then
  old_pid=$(tr -d '[:space:]' < "$PID_FILE")
  if [[ "$old_pid" =~ ^[0-9]+$ ]] && kill -0 "$old_pid" 2>/dev/null; then
    printf 'already_running pid=%s\n' "$old_pid"
    exit 0
  fi
fi

cd "$ROOT"
nohup bash "$SCRIPT_DIR/run_formal_e6_e8_background.sh" \
  > "$LOG_FILE" 2> "$ERR_FILE" < /dev/null &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"
printf 'started pid=%s log=%s err=%s\n' "$pid" "$LOG_FILE" "$ERR_FILE"
