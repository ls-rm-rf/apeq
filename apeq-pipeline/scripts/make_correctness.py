#!/usr/bin/env python3
"""Generate the P3 correctness matrix from party-B result rows."""

import argparse
import csv
import os
import subprocess
import sys
from collections import defaultdict

import validate as V


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out-prefix", default="p3-correctness")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--allow-commit", action="append", default=None)
    args = parser.parse_args()
    if not args.skip_validate:
        validator = os.path.join(os.path.dirname(__file__), "validate.py")
        command = [sys.executable, validator, args.csv]
        for commit in args.allow_commit or []:
            command.extend(["--allow-commit", commit])
        if subprocess.call(command) != 0:
            return 1

    report = V.Report()
    rows = V.load(args.csv, report)
    cells = defaultdict(lambda: [0, 0, 0, 0, 0])
    for row in rows:
        if row["party"] != "B":
            continue
        key = (row["protocol"], row["backend"], row["variant"],
               row["input_bits"], row["batch_size"])
        cell = cells[key]
        cell[0] += 1
        if row["status"] == "ok":
            cell[1] += 1
            cell[2] += row["batch_size"]
            cell[3] += max(0, row["n_false_pos"] or 0)
            cell[4] += max(0, row["n_false_neg"] or 0)

    output = [(*key, *values) for key, values in sorted(cells.items())]
    header = ["protocol", "backend", "variant", "input_bits", "batch_size",
              "executions", "ok_executions", "comparisons", "false_pos", "false_neg"]
    csv_path = args.out_prefix + ".csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(output)

    md_path = args.out_prefix + ".md"
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# P3 correctness matrix\n\n")
        handle.write("| Protocol | Variant | Bits | Batch | Runs | Comparisons | FP | FN |\n")
        handle.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in output:
            handle.write(f"| {row[0]} | {row[2]} | {row[3]} | {row[4]} | "
                         f"{row[6]}/{row[5]} | {row[7]} | {row[8]} | {row[9]} |\n")
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
