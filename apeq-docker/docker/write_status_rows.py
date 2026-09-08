#!/usr/bin/env python3
"""Write paired non-success rows when Docker kills or cannot complete a run."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

HEADER = [
    "run_id", "timestamp_utc", "git_commit", "hostname",
    "protocol", "backend", "variant",
    "batch_size", "input_bits", "field_bits", "security_param",
    "network", "rtt_ms", "bandwidth_mbps", "rep", "seed", "party",
    "setup_ms", "online_ms", "total_ms",
    "setup_bytes_sent", "setup_bytes_recv",
    "online_bytes_sent", "online_bytes_recv", "bytes_sent", "bytes_recv",
    "peak_rss_kb", "n_ot", "n_field_ops", "correct",
    "n_false_pos", "n_false_neg", "status", "note",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--protocol", required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--variant", required=True)
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--bits", type=int, required=True)
    ap.add_argument("--field-bits", type=int, required=True)
    ap.add_argument("--kappa", type=int, required=True)
    ap.add_argument("--network", required=True)
    ap.add_argument("--rtt", type=float, required=True)
    ap.add_argument("--bandwidth", type=float, required=True)
    ap.add_argument("--rep", type=int, required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--status", choices=("timeout", "oom", "crash", "skipped"), required=True)
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    note = args.note.replace(",", " ").replace("\n", " ").replace("\r", " ")

    for party in ("A", "B"):
        row = [
            args.run_id, now, "unknown", f"docker-party-{party}",
            args.protocol, args.backend, args.variant,
            args.batch, args.bits, args.field_bits, args.kappa,
            args.network, args.rtt, args.bandwidth, args.rep, args.seed, party,
            "", "", "", "", "", "", "", "", "", "", "", "", "",
            -1, -1, args.status, note,
        ]
        path = outdir / f"{args.run_id}-{party}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(HEADER)
            writer.writerow(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
