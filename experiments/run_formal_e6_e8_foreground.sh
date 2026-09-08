#!/usr/bin/env bash
set -eu

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
printf '%s\n' "$$" > "$ROOT/.formal-e6-e8-mixed.pid"
exec bash "$SCRIPT_DIR/run_formal_e6_e8_background.sh" \
  > "$ROOT/formal-e6-e8-mixed.log" \
  2> "$ROOT/formal-e6-e8-mixed.err.log"
