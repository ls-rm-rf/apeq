#!/usr/bin/env python3
"""Report the measured APEQ-OLE/VOLE communication crossover."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--out-prefix", default="formal-e6-communication-crossover-final")
    args = parser.parse_args()

    wanted = {100, 200, 400, 800, 1000}
    cells = defaultdict(list)
    revisions = defaultdict(set)
    with args.csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            batch = int(row["batch_size"])
            if (row["protocol"] != "apeq" or row["party"] != "B" or
                    row["status"] != "ok" or batch not in wanted):
                continue
            key = (row["variant"], batch)
            cells[key].append(int(row["bytes_sent"]) + int(row["bytes_recv"]))
            revisions[key].add(row["git_commit"])

    output = []
    for key in sorted(cells, key=lambda item: (item[1], item[0])):
        values = cells[key]
        mean = sum(values) / len(values)
        output.append({
            "variant": key[0],
            "batch_size": key[1],
            "samples": len(values),
            "mean_bytes": mean,
            "min_bytes": min(values),
            "max_bytes": max(values),
            "bytes_per_comparison": mean / key[1],
            "revisions": ";".join(sorted(revisions[key])),
        })

    by_batch = defaultdict(dict)
    for row in output:
        by_batch[row["batch_size"]][row["variant"]] = row["mean_bytes"]
    differences = []
    for batch in sorted(by_batch):
        if {"ole", "vole_hash"} <= set(by_batch[batch]):
            differences.append((
                batch,
                by_batch[batch]["vole_hash"] - by_batch[batch]["ole"],
            ))

    bracket = None
    estimate = None
    for left, right in zip(differences, differences[1:]):
        if left[1] >= 0 and right[1] <= 0:
            bracket = (left[0], right[0])
            estimate = left[0] + left[1] * (right[0] - left[0]) / (left[1] - right[1])
            break

    csv_path = Path(args.out_prefix + ".csv")
    md_path = Path(args.out_prefix + ".md")
    fields = [
        "variant", "batch_size", "samples", "mean_bytes", "min_bytes",
        "max_bytes", "bytes_per_comparison", "revisions",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output)

    with md_path.open("w", encoding="utf-8") as handle:
        handle.write("# E6 APEQ communication crossover\n\n")
        handle.write("Communication is Party B's application-payload sent+received total. "
                     "Each cell pools six widths, LAN/WAN, and ten repetitions.\n\n")
        handle.write("| Batch | OLE bytes | VOLE bytes | VOLE - OLE |\n")
        handle.write("|---:|---:|---:|---:|\n")
        for batch, difference in differences:
            handle.write(
                f"| {batch} | {by_batch[batch]['ole']:.0f} | "
                f"{by_batch[batch]['vole_hash']:.0f} | {difference:+.0f} |\n"
            )
        if bracket is not None:
            handle.write(
                f"\nThe measured crossover is bracketed by batch {bracket[0]} and "
                f"{bracket[1]}. Linear interpolation gives approximately "
                f"{estimate:.0f}; this is an estimate, not a directly measured "
                "integer crossover.\n"
            )
        else:
            handle.write("\nNo sign-changing crossover was observed in the measured points.\n")
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
