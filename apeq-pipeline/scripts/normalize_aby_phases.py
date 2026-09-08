#!/usr/bin/env python3
"""Canonicalize ABY receive-phase counters from peer sender attribution.

ABY sends through background threads.  A message is correctly attributed when
the protocol enqueues it, while the peer receive counter can cross the local
setup/online snapshot under RTT.  The raw input is never modified.  For ABY
rows only, this tool treats each direction's sender counters as authoritative
and copies them to the peer's receive counters.  All other fields and protocols
are preserved.
"""

import argparse
import csv
import os
import subprocess
import sys
from collections import defaultdict


PHASES = ("setup", "online")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("output_csv")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--allow-commit", action="append", default=None)
    args = parser.parse_args()

    source = os.path.realpath(os.path.abspath(args.input_csv))
    destination = os.path.realpath(os.path.abspath(args.output_csv))
    if source == destination:
        parser.error("output must differ from the raw input CSV")

    with open(source, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            parser.error("input CSV has no header")
        fieldnames = reader.fieldnames
        rows = list(reader)

    by_run = defaultdict(list)
    for row in rows:
        by_run[row["run_id"]].append(row)

    reconciled = 0
    for run_id, pair in by_run.items():
        if len(pair) != 2:
            continue
        parties = {row["party"]: row for row in pair}
        if set(parties) != {"A", "B"}:
            continue
        a = parties["A"]
        b = parties["B"]
        if a["protocol"] != "aby_eq" or b["protocol"] != "aby_eq":
            continue
        if a["status"] != "ok" or b["status"] != "ok":
            continue

        # Sender attribution defines phase membership.  Only receive-side
        # counters are canonicalized; sender measurements remain untouched.
        for receiver, sender in ((a, b), (b, a)):
            for phase in PHASES:
                receiver[f"{phase}_bytes_recv"] = sender[
                    f"{phase}_bytes_sent"
                ]
            receiver["bytes_recv"] = sender["bytes_sent"]
            marker = "aby_recv_phase_from_peer_sender"
            if marker not in receiver["note"].split():
                receiver["note"] = (receiver["note"] + " " + marker).strip()
        reconciled += 1

    os.makedirs(os.path.dirname(destination) or ".", exist_ok=True)
    with open(destination, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {destination}")
    print(f"canonicalized ABY executions: {reconciled}")
    if args.skip_validate:
        return 0
    validator = os.path.join(os.path.dirname(__file__), "validate.py")
    command = [sys.executable, validator, destination]
    for commit in args.allow_commit or []:
        command.extend(["--allow-commit", commit])
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
