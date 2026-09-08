#!/usr/bin/env python3
"""Merge non-overlapping normalized result CSVs without changing provenance."""

import argparse
import csv
from pathlib import Path


KEY_FIELDS = (
    "protocol", "backend", "variant", "batch_size", "input_bits",
    "field_bits", "security_param", "network", "rtt_ms", "bandwidth_mbps",
    "rep", "party",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    header = None
    rows = []
    seen = set()
    for path in args.inputs:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if header is None:
                header = reader.fieldnames
            elif reader.fieldnames != header:
                raise SystemExit(f"header mismatch: {path}")
            for row in reader:
                key = tuple(row[field] for field in KEY_FIELDS)
                if key in seen:
                    raise SystemExit(f"duplicate configuration in {path}: {key}")
                seen.add(key)
                rows.append(row)

    rows.sort(key=lambda row: (
        row["network"], float(row["rtt_ms"]), row["protocol"], row["variant"],
        int(row["input_bits"]), int(row["batch_size"]), int(row["rep"]),
        row["party"], row["run_id"],
    ))
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    revisions = sorted({row["git_commit"] for row in rows})
    print(f"wrote {args.output}: rows={len(rows)} revisions={','.join(revisions)}")


if __name__ == "__main__":
    main()
