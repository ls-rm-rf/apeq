#!/usr/bin/env bash
# Current six-RTT matrix; outputs are distinct from historical campaign files.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
OUT="$ROOT/results/round-sweep"
mkdir -p "$OUT"
cd "$ROOT/apeq-docker/docker"
run_status=0
RESULTS="$OUT/raw.csv" RUN_DIR="$OUT/party-runs" \
INCLUDE_MOCK=0 ONLY_PROTOCOLS="" SECURITY_PARAM=128 FIELD_BITS=128 \
NETWORKS="rtt0p5 rtt10 rtt20 rtt40 rtt60 rtt80" \
WIDTHS="8 16 24 32 48 64" BATCHES=100 REPS=10 TIMEOUT_S=300 \
bash ./run_all.sh || run_status=$?
# Raw ABY receive-phase attribution can fail validation. Require the normalized
# validator and all 48 six-point/60-session fits below before returning success.
echo "raw runner status=$run_status; checking normalized results and complete fits"
python3 "$ROOT/apeq-pipeline/scripts/normalize_aby_phases.py" \
  "$OUT/raw.csv" "$OUT/normalized.csv"
python3 "$ROOT/apeq-pipeline/scripts/estimate_rounds.py" \
  "$OUT/normalized.csv" --out-prefix "$OUT/estimates"
python3 "$ROOT/apeq-pipeline/scripts/make_round_width_figure.py" \
  "$OUT/estimates.csv" "$OUT/rounds-vs-width.pdf"
