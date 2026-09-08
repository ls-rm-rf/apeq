#!/usr/bin/env bash
# Run the baseline matrix on a Linux Docker host.
# Each execution starts both parties on an isolated Docker network. Parties
# write separate files; the host merges them only after both containers exit.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
VALIDATOR="$PROJECT_ROOT/apeq-pipeline/scripts/validate.py"
STATUS_WRITER="$SCRIPT_DIR/write_status_rows.py"

RESULTS="${RESULTS:-$SCRIPT_DIR/results.csv}"
RUN_DIR="${RUN_DIR:-$SCRIPT_DIR/party-runs}"
TIMEOUT_S="${TIMEOUT_S:-300}"
APPLY_NETEM="${APPLY_NETEM:-1}"
REPS="${REPS:-10}"
BATCHES="${BATCHES:-1 10 48 96 100 1000 10000}"
# The shared harness stores two limbs. Defaults stay within the common
# third-party adapter range; APEQ-only runs may explicitly request 120/126.
# 128 is intentionally forbidden because p=2^127-1 cannot embed it injectively.
WIDTHS="${WIDTHS:-8 16 24 32 48 64}"
NETWORKS="${NETWORKS:-lan wan}"
FIELD_BITS="${FIELD_BITS:-128}"
SECURITY_PARAM="${SECURITY_PARAM:-128}"
OLE_N="${OLE_N:-1024}"
OLE_RHO="${OLE_RHO:-769}"
OLE_ELL="${OLE_ELL:-255}"
OLE_K="${OLE_K:-128}"
OLE_T="${OLE_T:-48}"
# Space-separated protocol names; empty means all entries below.
ONLY_PROTOCOLS="${ONLY_PROTOCOLS:-}"
# Space-separated variant names; empty means all variants for selected protocols.
ONLY_VARIANTS="${ONLY_VARIANTS:-}"
# Opt-in harness smoke row. It is labelled apeq/ips_ole/ole so the existing
# structural validator exercises its APEQ lower bound; it is never included in
# a baseline matrix unless explicitly requested.
INCLUDE_MOCK="${INCLUDE_MOCK:-0}"

# protocol|image|backend|variant|field_bits.
PROTOCOLS=(
  "apeq|apeq/apeq|ips_ole|ole|127"
  "apeq|apeq/apeq-vole|ferret_vole|vole_hash|128"
  "lu_eq|apeq/lu|n/a|n/a|128"
  "emp_eq|apeq/emp|n/a|n/a|${FIELD_BITS}"
  "aby_eq|apeq/aby|n/a|yao|${FIELD_BITS}"
  "aby_eq|apeq/aby|n/a|gmw|${FIELD_BITS}"
  "cryptflow2_eq|apeq/cryptflow2|n/a|n/a|${FIELD_BITS}"
  "volepsi_eq|apeq/volepsi|n/a|n/a|128"
)
if [[ "$INCLUDE_MOCK" == "1" ]]; then
  PROTOCOLS=("apeq|apeq/mock|ips_ole|ole|127" "${PROTOCOLS[@]}")
fi

for cmd in docker python3 timeout; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing required command: $cmd" >&2
    exit 2
  }
done
[[ "$APPLY_NETEM" == "0" || "$APPLY_NETEM" == "1" ]] || {
  echo "APPLY_NETEM must be 0 or 1" >&2
  exit 2
}
[[ -f "$VALIDATOR" ]] || { echo "validator not found: $VALIDATOR" >&2; exit 2; }
[[ -f "$STATUS_WRITER" ]] || { echo "status writer not found: $STATUS_WRITER" >&2; exit 2; }
# Docker interprets a relative `-v source:/out` source as a named volume, so
# make both host-side output paths absolute before any container is started.
RESULTS="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$RESULTS")"
RUN_DIR="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$RUN_DIR")"
mkdir -p "$RUN_DIR" "$(dirname -- "$RESULTS")"

network_params() {
  case "$1" in
    lan)      echo "0.25ms 1000mbit 0.5 1000 lan" ;;
    wan)      echo "40ms 100mbit 80 100 wan" ;;
    rtt0p5)  echo "0.25ms 1000mbit 0.5 1000 round_sweep" ;;
    rtt10)   echo "5ms 1000mbit 10 1000 round_sweep" ;;
    rtt20)   echo "10ms 1000mbit 20 1000 round_sweep" ;;
    rtt40)   echo "20ms 1000mbit 40 1000 round_sweep" ;;
    rtt60)   echo "30ms 1000mbit 60 1000 round_sweep" ;;
    rtt80)   echo "40ms 1000mbit 80 1000 round_sweep" ;;
    *) echo "unknown network profile: $1" >&2; return 1 ;;
  esac
}

already_done() {
  local proto="$1" backend="$2" variant="$3" batch="$4" bits="$5" field_bits="$6"
  local net="$7" rtt="$8" bandwidth="$9" rep="${10}"
  [[ -f "$RESULTS" ]] || return 1
  awk -F, -v p="$proto" -v be="$backend" -v v="$variant" -v ba="$batch" \
      -v bi="$bits" -v fb="$field_bits" -v n="$net" -v rt="$rtt" \
      -v bw="$bandwidth" -v r="$rep" '
        NR > 1 && $5 == p && $6 == be && $7 == v && $8 == ba &&
        $9 == bi && $10 == fb && $12 == n && $13 == rt && $14 == bw &&
        $15 == r { seen[$17] = 1 }
        END { exit !(seen["A"] && seen["B"]) }
      ' "$RESULTS"
}

append_party_file() {
  local src="$1"
  [[ -s "$src" ]] || { echo "missing result file: $src" >&2; return 1; }
  if [[ ! -f "$RESULTS" ]]; then
    cp "$src" "$RESULTS"
  else
    tail -n +2 "$src" >> "$RESULTS"
  fi
}

cleanup_run() {
  local a_name="$1" b_name="$2" docker_net="$3"
  docker rm -f "$a_name" "$b_name" >/dev/null 2>&1 || true
  docker network rm "$docker_net" >/dev/null 2>&1 || true
}

run_pair() {
  local proto="$1" image="$2" backend="$3" variant="$4" field_bits="$5"
  local batch="$6" bits="$7" profile="$8" rep="$9"
  local delay rate rtt bandwidth net
  read -r delay rate rtt bandwidth net < <(network_params "$profile") || return 1

  local run_id seed short docker_net a_name b_name a_file b_file wait_file
  run_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
  seed="$(python3 -c 'import hashlib,sys; x=hashlib.sha256(sys.argv[1].encode()).digest()[:8]; print(int.from_bytes(x,"big") or 1)' \
      "$proto|$backend|$variant|$batch|$bits|$net|$rep|$OLE_N|$OLE_RHO|$OLE_ELL|$OLE_K|$OLE_T")"
  short="${run_id:0:8}"
  docker_net="apeq-$short"
  a_name="apeq-a-$short"
  b_name="apeq-b-$short"
  a_file="$RUN_DIR/$run_id-A.csv"
  b_file="$RUN_DIR/$run_id-B.csv"
  wait_file="$RUN_DIR/$run_id.wait"
  rm -f "$a_file" "$b_file" "$wait_file"

  docker image inspect "$image" >/dev/null 2>&1 || {
    echo "image not built: $image" >&2
    return 1
  }
  docker network create "$docker_net" >/dev/null || return 1

  local common=(
    --protocol "$proto" --backend "$backend" --variant "$variant"
    --batch "$batch" --bits "$bits" --field-bits "$field_bits"
    --ole-n "$OLE_N" --ole-rho "$OLE_RHO" --ole-ell "$OLE_ELL"
    --ole-k "$OLE_K" --ole-t "$OLE_T"
    --kappa "$SECURITY_PARAM" --network "$net" --rtt "$rtt"
    --bandwidth "$bandwidth" --rep "$rep" --seed "$seed"
    --run-id "$run_id" --port 12345 --note "netem_${net}_tdsc_params"
  )
  local shell_wrapper
  local -a wrapper_args
  if [[ "$APPLY_NETEM" == "1" ]]; then
    # The experiment models RTT and bottleneck rate, not packet loss.  netem's
    # default 1000-packet queue is smaller than some intentionally batched APEQ
    # messages and would otherwise create artificial drops/TCP retransmissions.
    shell_wrapper='tc qdisc replace dev eth0 root netem limit 100000 delay "$1" rate "$2" || exit 90; shift 2; exec /opt/bench/driver "$@"'
    wrapper_args=(sh "$delay" "$rate")
  else
    shell_wrapper='exec /opt/bench/driver "$@"'
    wrapper_args=(sh)
  fi

  docker run -d --name "$a_name" --network "$docker_net" --cap-add NET_ADMIN \
    -v "$RUN_DIR:/out" --entrypoint /bin/sh "$image" \
    -c "$shell_wrapper" "${wrapper_args[@]}" "${common[@]}" \
    --party 1 --host 0.0.0.0 --out "/out/$run_id-A.csv" >/dev/null || {
      cleanup_run "$a_name" "$b_name" "$docker_net"; return 1;
    }

  local a_ip
  a_ip="$(docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$a_name")"
  [[ -n "$a_ip" ]] || { cleanup_run "$a_name" "$b_name" "$docker_net"; return 1; }

  docker run -d --name "$b_name" --network "$docker_net" --cap-add NET_ADMIN \
    -v "$RUN_DIR:/out" --entrypoint /bin/sh "$image" \
    -c "$shell_wrapper" "${wrapper_args[@]}" "${common[@]}" \
    --party 2 --host "$a_ip" --out "/out/$run_id-B.csv" >/dev/null || {
      cleanup_run "$a_name" "$b_name" "$docker_net"; return 1;
    }

  local timed_out=0 rc_a=1 rc_b=1
  if timeout "${TIMEOUT_S}s" docker wait "$a_name" "$b_name" > "$wait_file"; then
    rc_a="$(docker inspect --format '{{.State.ExitCode}}' "$a_name")"
    rc_b="$(docker inspect --format '{{.State.ExitCode}}' "$b_name")"
  else
    timed_out=1
  fi

  if (( timed_out )); then
    echo "  timeout after ${TIMEOUT_S}s"
    cleanup_run "$a_name" "$b_name" "$docker_net"
    python3 "$STATUS_WRITER" --outdir "$RUN_DIR" --run-id "$run_id" \
      --protocol "$proto" --backend "$backend" --variant "$variant" \
      --batch "$batch" --bits "$bits" --field-bits "$field_bits" \
      --kappa "$SECURITY_PARAM" --network "$net" --rtt "$rtt" \
      --bandwidth "$bandwidth" --rep "$rep" --seed "$seed" \
      --status timeout --note "killed_after_${TIMEOUT_S}s"
  else
    if [[ "$rc_a" != 0 || "$rc_b" != 0 ]]; then
      echo "  party exit codes: A=$rc_a B=$rc_b" >&2
      docker logs "$a_name" >&2 || true
      docker logs "$b_name" >&2 || true
      if [[ ! -s "$a_file" || ! -s "$b_file" ]]; then
        python3 "$STATUS_WRITER" --outdir "$RUN_DIR" --run-id "$run_id" \
          --protocol "$proto" --backend "$backend" --variant "$variant" \
          --batch "$batch" --bits "$bits" --field-bits "$field_bits" \
          --kappa "$SECURITY_PARAM" --network "$net" --rtt "$rtt" \
          --bandwidth "$bandwidth" --rep "$rep" --seed "$seed" \
          --status crash --note "container_exit_A${rc_a}_B${rc_b}"
      fi
    fi
    cleanup_run "$a_name" "$b_name" "$docker_net"
  fi

  append_party_file "$a_file" && append_party_file "$b_file"
}

for profile in $NETWORKS; do
  read -r _ _ profile_rtt profile_bandwidth profile_net < <(network_params "$profile") || exit 1
  for entry in "${PROTOCOLS[@]}"; do
    IFS='|' read -r proto image backend variant protocol_field_bits <<< "$entry"
    if [[ -n "$ONLY_PROTOCOLS" && " $ONLY_PROTOCOLS " != *" $proto "* ]]; then
      continue
    fi
    if [[ -n "$ONLY_VARIANTS" && " $ONLY_VARIANTS " != *" $variant "* ]]; then
      continue
    fi
    for bits in $WIDTHS; do
      for batch in $BATCHES; do
        for rep in $(seq 0 $((REPS - 1))); do
          if already_done "$proto" "$backend" "$variant" "$batch" "$bits" \
              "$protocol_field_bits" "$profile_net" "$profile_rtt" \
              "$profile_bandwidth" "$rep"; then
            echo "[skip] $profile $proto/$variant bits=$bits batch=$batch rep=$rep"
            continue
          fi
          echo "[run]  $profile $proto/$variant bits=$bits batch=$batch rep=$rep"
          run_pair "$proto" "$image" "$backend" "$variant" "$protocol_field_bits" \
            "$batch" "$bits" "$profile" "$rep" || {
            echo "run failed before a complete A/B record was produced" >&2
            exit 1
          }
        done
      done
    done
  done
done

echo "validating $RESULTS"
python3 "$VALIDATOR" "$RESULTS"
