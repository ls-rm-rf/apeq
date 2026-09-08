#!/usr/bin/env python3
"""Replace every APEQ/OLE row in a validated baseline matrix."""

import argparse
import csv
from collections import Counter
from pathlib import Path


def read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def is_ole(row):
    return (row["protocol"], row["backend"], row["variant"]) == (
        "apeq", "ips_ole", "ole")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("replacement", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--bits", nargs="+", type=int)
    parser.add_argument("--batches", nargs="+", type=int)
    parser.add_argument(
        "--cell", action="append", default=[], metavar="BITS:BATCH",
        help="repeat to specify a non-Cartesian measurement slice")
    parser.add_argument("--networks", nargs="+", required=True)
    parser.add_argument("--reps", type=int, default=10)
    args = parser.parse_args()
    if args.out.resolve() in (args.base.resolve(), args.replacement.resolve()):
        parser.error("output must not overwrite an input archive file")

    base = read(args.base)
    replacement = read(args.replacement)
    if not base or not replacement:
        raise SystemExit("both input files must contain data rows")
    if any(not is_ole(row) for row in replacement):
        raise SystemExit("replacement contains a non-APEQ/OLE row")
    if any(row["status"] != "ok" or row["correct"].lower() != "true"
           for row in replacement):
        raise SystemExit("replacement contains an unsuccessful or incorrect row")
    if any(row["n_false_pos"] not in ("0", "-1") or
           row["n_false_neg"] not in ("0", "-1")
           for row in replacement):
        raise SystemExit("replacement contains a recorded equality error")

    commits = {row["git_commit"] for row in replacement}
    if len(commits) != 1 or "unknown" in commits or "" in commits:
        raise SystemExit(f"replacement provenance is invalid: {sorted(commits)}")

    if args.cell:
        expected_cells = set()
        for value in args.cell:
            width, batch = value.split(":", 1)
            expected_cells.add((int(width), int(batch)))
    elif args.bits and args.batches:
        expected_cells = {(bits, batch) for bits in args.bits
                          for batch in args.batches}
    else:
        raise SystemExit("provide --cell entries or both --bits and --batches")

    keys = Counter(
        (row["network"], int(row["input_bits"]), int(row["batch_size"]),
         int(row["rep"]), row["party"])
        for row in replacement
    )
    expected = {
        (network, bits, batch, rep, party)
        for network in args.networks
        for bits, batch in expected_cells
        for rep in range(args.reps)
        for party in ("A", "B")
    }
    actual = set(keys)
    duplicates = sorted(key for key, count in keys.items() if count != 1)
    if actual != expected or duplicates:
        missing = sorted(expected - actual)[:10]
        extra = sorted(actual - expected)[:10]
        raise SystemExit(
            f"replacement grid mismatch: missing={missing} extra={extra} "
            f"duplicate={duplicates[:10]}")

    old_count = sum(is_ole(row) for row in base)
    combined = [row for row in base if not is_ole(row)] + replacement
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)
    print(f"replaced {old_count} rows with {len(replacement)} rows")
    print(f"wrote {len(combined)} rows to {args.out}")
    print(f"replacement revision: {next(iter(commits))}")


if __name__ == "__main__":
    main()
