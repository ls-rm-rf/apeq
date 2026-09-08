#!/usr/bin/env bash
# E3/E4: capture one 64-bit, batch-100, RTT-20 execution per variant.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
AUDIT_TAG="${AUDIT_TAG:-8251}"
ONLY_CASES="${ONLY_CASES:-}"
OUTDIR="$ROOT/tcpdump-audit-$AUDIT_TAG"
RESULTS="$OUTDIR/results-raw.csv"
NORMALIZED="$OUTDIR/results-normalized.csv"
METADATA="$OUTDIR/captures.tsv"
VALIDATOR="$ROOT/apeq-pipeline/scripts/validate.py"
NORMALIZER="$ROOT/apeq-pipeline/scripts/normalize_aby_phases.py"
STATUS_WRITER="$ROOT/apeq-docker/docker/write_status_rows.py"
CAPTURE_IMAGE=apeq/emp
PORT=12345
DELAY=10ms
RATE=1000mbit
RTT=20
BANDWIDTH=1000
BATCH=100
BITS=64
KAPPA=128

PROTOCOLS=(
  "apeq|apeq/apeq|ips_ole|ole|127"
  "apeq|apeq/apeq-vole|ferret_vole|vole_hash|128"
  "lu_eq|apeq/lu|n/a|n/a|128"
  "emp_eq|apeq/emp|n/a|n/a|128"
  "aby_eq|apeq/aby|n/a|yao|128"
  "aby_eq|apeq/aby|n/a|gmw|128"
  "cryptflow2_eq|apeq/cryptflow2|n/a|n/a|128"
  "volepsi_eq|apeq/volepsi|n/a|n/a|128"
)

[[ ! -e "$OUTDIR" ]] || {
  echo "refusing to overwrite existing $OUTDIR" >&2
  exit 2
}
mkdir -p "$OUTDIR"
printf 'run_id\tprotocol\tbackend\tvariant\ta_ip\tb_ip\tpcap\tpackets\n' > "$METADATA"

append_party_file() {
  local source="$1"
  if [[ ! -f "$RESULTS" ]]; then
    cp "$source" "$RESULTS"
  else
    tail -n +2 "$source" >> "$RESULTS"
  fi
}

for entry in "${PROTOCOLS[@]}"; do
  IFS='|' read -r proto image backend variant field_bits <<< "$entry"
  case_name="$proto/$variant"
  if [[ -n "$ONLY_CASES" && " $ONLY_CASES " != *" $case_name "* ]]; then
    continue
  fi
  run_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  seed="$(python3 -c 'import hashlib,sys; d=hashlib.sha256(sys.argv[1].encode()).digest()[:8]; print(int.from_bytes(d,"big") or 1)' \
    "tcpdump|$proto|$backend|$variant|$BATCH|$BITS")"
  short="${run_id:0:8}"
  docker_net="apeq-cap-$short"
  a_name="apeq-cap-a-$short"
  b_name="apeq-cap-b-$short"
  cap_name="apeq-cap-sniffer-$short"
  a_file="$OUTDIR/$run_id-A.csv"
  b_file="$OUTDIR/$run_id-B.csv"
  pcap_name="$short.pcap"
  packets_name="$short.packets.txt"

  cleanup() {
    docker rm -f "$cap_name" "$a_name" "$b_name" >/dev/null 2>&1 || true
    docker network rm "$docker_net" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT

  echo "[capture] $proto/$variant"
  docker network create "$docker_net" >/dev/null
  network_id="$(docker network inspect --format '{{.Id}}' "$docker_net")"
  bridge="br-${network_id:0:12}"
  common=(
    --protocol "$proto" --backend "$backend" --variant "$variant"
    --batch "$BATCH" --bits "$BITS" --field-bits "$field_bits"
    --kappa "$KAPPA" --network round_sweep --rtt "$RTT"
    --bandwidth "$BANDWIDTH" --rep 0 --seed "$seed"
    --run-id "$run_id" --port "$PORT" --note tcpdump_rtt20
  )
  wrapper='tc qdisc replace dev eth0 root netem limit 100000 delay "$1" rate "$2" || exit 90; shift 2; exec /opt/bench/driver "$@"'

  # Capture the host-side Docker bridge, not either party's network namespace.
  # This keeps tcpdump alive while both netem queues drain and the party
  # containers exit.
  docker run -d --name "$cap_name" --network host \
    --cap-add NET_RAW --cap-add NET_ADMIN -v "$OUTDIR:/capture" \
    --entrypoint /usr/bin/tcpdump "$CAPTURE_IMAGE" \
    -i "$bridge" -U -n -s 0 -w "/capture/$pcap_name" tcp >/dev/null
  for _ in $(seq 1 100); do
    docker logs "$cap_name" 2>&1 | grep -q "listening on $bridge" && break
    sleep 0.05
  done
  docker logs "$cap_name" 2>&1 | grep -q "listening on $bridge" || {
    echo "tcpdump did not become ready" >&2
    exit 3
  }

  docker run -d --name "$a_name" --network "$docker_net" --cap-add NET_ADMIN \
    -v "$OUTDIR:/out" --entrypoint /bin/sh "$image" \
    -c "$wrapper" sh "$DELAY" "$RATE" "${common[@]}" \
    --party 1 --host 0.0.0.0 --out "/out/$run_id-A.csv" >/dev/null
  a_ip="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$a_name")"

  docker run -d --name "$b_name" --network "$docker_net" --cap-add NET_ADMIN \
    -v "$OUTDIR:/out" --entrypoint /bin/sh "$image" \
    -c "$wrapper" sh "$DELAY" "$RATE" "${common[@]}" \
    --party 2 --host "$a_ip" --out "/out/$run_id-B.csv" >/dev/null
  b_ip="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$b_name")"

  if ! timeout 300s docker wait "$a_name" "$b_name" > "$OUTDIR/$short.wait"; then
    echo "protocol timeout" >&2
    exit 4
  fi
  rc_a="$(docker inspect --format '{{.State.ExitCode}}' "$a_name")"
  rc_b="$(docker inspect --format '{{.State.ExitCode}}' "$b_name")"
  if [[ "$rc_a" != 0 || "$rc_b" != 0 ]]; then
    docker logs "$a_name" >&2 || true
    docker logs "$b_name" >&2 || true
    echo "party exit codes A=$rc_a B=$rc_b" >&2
    exit 5
  fi

  # The parties have finished, so this delay cannot affect protocol metrics.
  # It lets tcpdump drain packets already accepted by the kernel filter before
  # SIGINT; otherwise high-packet-count ABY captures can be truncated despite
  # reporting zero kernel drops.
  sleep 3
  if [[ "$(docker inspect --format '{{.State.Running}}' "$cap_name")" == true ]]; then
    docker kill --signal=INT "$cap_name" >/dev/null || true
  fi
  docker wait "$cap_name" >/dev/null || true
  docker logs "$cap_name" > "$OUTDIR/$short.tcpdump.log" 2>&1 || true
  docker run --rm -v "$OUTDIR:/capture:ro" \
    --entrypoint /usr/bin/tcpdump "$CAPTURE_IMAGE" \
    -nn -tt -S -r "/capture/$pcap_name" tcp \
    > "$OUTDIR/$packets_name" 2> "$OUTDIR/$short.read.log"

  append_party_file "$a_file"
  append_party_file "$b_file"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$run_id" "$proto" "$backend" "$variant" "$a_ip" "$b_ip" \
    "$pcap_name" "$packets_name" >> "$METADATA"

  cleanup
  trap - EXIT
done

# Raw ABY phase attribution can be asynchronous; retain raw and normalize with
# the same audited rule used by the formal matrices.
python3 "$NORMALIZER" "$RESULTS" "$NORMALIZED"
python3 "$VALIDATOR" "$NORMALIZED"
echo "captures complete: $OUTDIR"
