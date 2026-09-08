#!/usr/bin/env python3
"""Replace obsolete APEQ/OLE RTT-sweep rows with the corrected c=8 runs."""

import argparse
import csv
from pathlib import Path


def load(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline", type=Path)
    parser.add_argument("replacement", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.resolve() in (args.baseline.resolve(), args.replacement.resolve()):
        parser.error("output must not overwrite an input archive file")

    fields, baseline = load(args.baseline)
    replacement_fields, replacement = load(args.replacement)
    if fields != replacement_fields:
        raise SystemExit("CSV schemas differ")

    obsolete = [
        row for row in baseline
        if row["protocol"] == "apeq" and row["variant"] == "ole"
    ]
    retained = [row for row in baseline if row not in obsolete]

    if len(obsolete) != 720:
        raise SystemExit(f"expected 720 obsolete rows, found {len(obsolete)}")
    if len(replacement) != 720:
        raise SystemExit(f"expected 720 replacement rows, found {len(replacement)}")
    if any(row["protocol"] != "apeq" or row["variant"] != "ole"
           for row in replacement):
        raise SystemExit("replacement contains a non-APEQ/OLE row")
    if {row["git_commit"] for row in replacement} != {"tree-05290e9816c7"}:
        raise SystemExit("replacement revision is not tree-05290e9816c7")

    expected_cells = {
        (str(bits), f"{rtt:.3f}")
        for bits in (8, 16, 24, 32, 48, 64)
        for rtt in (0.5, 10, 20, 40, 60, 80)
    }
    actual_cells = {(row["input_bits"], row["rtt_ms"]) for row in replacement}
    if actual_cells != expected_cells:
        raise SystemExit("replacement does not cover the expected width/RTT cells")
    for cell in expected_cells:
        rows = [row for row in replacement
                if (row["input_bits"], row["rtt_ms"]) == cell]
        if len(rows) != 20 or {row["party"] for row in rows} != {"A", "B"}:
            raise SystemExit(f"incomplete replacement cell: {cell}")

    combined = retained + replacement
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(combined)

    print(f"removed {len(obsolete)} obsolete rows")
    print(f"added {len(replacement)} corrected rows")
    print(f"wrote {len(combined)} rows to {args.output}")


if __name__ == "__main__":
    main()
