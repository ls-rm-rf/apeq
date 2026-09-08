#!/usr/bin/env python3
"""Fit per-RTT means of the larger local phase duration against RTT."""

import argparse
import csv
import math
import os
import subprocess
import sys
from collections import defaultdict

import validate as V


def fit(points):
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("RTT values are identical")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in points) / sxx
    intercept = y_mean - slope * x_mean
    residual = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    total = sum((y - y_mean) ** 2 for y in ys)
    r2 = 1.0 if total == 0 and residual == 0 else 1.0 - residual / total
    return slope, intercept, r2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out-prefix", default="round-estimates")
    parser.add_argument("--skip-validate", action="store_true")
    parser.add_argument("--allow-commit", action="append", default=None)
    args = parser.parse_args()

    csv_path = args.out_prefix + ".csv"
    md_path = args.out_prefix + ".md"
    input_path = os.path.realpath(os.path.abspath(args.csv))
    for output_path in (csv_path, md_path):
        if os.path.realpath(os.path.abspath(output_path)) == input_path:
            parser.error(
                "output would overwrite the input CSV; choose a different "
                "--out-prefix"
            )

    if not args.skip_validate:
        validator = os.path.join(os.path.dirname(__file__), "validate.py")
        command = [sys.executable, validator, args.csv]
        for commit in args.allow_commit or []:
            command.extend(["--allow-commit", commit])
        if subprocess.call(command) != 0:
            return 1

    report = V.Report()
    rows = V.load(args.csv, report)
    by_run = defaultdict(list)
    for row in rows:
        if row["status"] == "ok" and row["network"] == "round_sweep":
            by_run[row["run_id"]].append(row)

    samples = defaultdict(lambda: defaultdict(list))
    for run_id, pair in by_run.items():
        if len(pair) != 2:
            continue
        first = pair[0]
        key = (first["protocol"], first["backend"], first["variant"],
               first["batch_size"], first["input_bits"], first["field_bits"],
               first["security_param"], first["bandwidth_mbps"])
        rtt = first["rtt_ms"]
        samples[key][rtt].append({
            metric: max(row[metric] for row in pair)
            for metric in ("setup_ms", "online_ms", "total_ms")
        })

    output = []
    for key, by_rtt in sorted(samples.items()):
        if len(by_rtt) < 3:
            continue
        means = {}
        for rtt, values in by_rtt.items():
            means[rtt] = {
                metric: sum(value[metric] for value in values) / len(values)
                for metric in ("setup_ms", "online_ms", "total_ms")
            }
        fitted = {}
        for metric in ("setup_ms", "online_ms", "total_ms"):
            fitted[metric] = fit(sorted((rtt, value[metric])
                                        for rtt, value in means.items()))
        output.append((*key, len(by_rtt), sum(len(v) for v in by_rtt.values()),
                       *fitted["setup_ms"], *fitted["online_ms"],
                       *fitted["total_ms"]))

    header = ["protocol", "backend", "variant", "batch_size", "input_bits",
              "field_bits", "security_param", "bandwidth_mbps", "n_rtt",
              "n_runs", "setup_rounds", "setup_intercept_ms", "setup_r2",
              "online_rounds", "online_intercept_ms", "online_r2",
              "total_rounds", "total_intercept_ms", "total_r2"]
    with open(csv_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(output)

    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("# Effective RTT-count estimates\n\n")
        handle.write("For each execution, take the larger local phase duration max(A,B), "
                     "then fit its per-RTT means against configured RTT. R² is computed "
                     "on those means, not on individual executions. The CSV records "
                     "the bandwidth, number of RTT levels and execution count.\n\n")
        handle.write(
            "These slopes measure transport sensitivity of the recorded phase "
            "durations. Local timers need not start together, so their maximum is "
            "not the interval from the earliest start to the latest finish. "
            "These slopes are not automatically protocol message-round "
            "counts: asymmetric phase entry can move peer-waiting time between "
            "setup and online. Use packet-transcript evidence when making a "
            "message-dependency claim.\n\n"
        )
        handle.write("| Protocol | Variant | Batch | Bits | Setup RTTs | Online RTTs | Total RTTs | Total R² |\n")
        handle.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in output:
            handle.write(f"| {row[0]} | {row[2]} | {row[3]} | {row[4]} | "
                         f"{row[10]:.2f} | {row[13]:.2f} | {row[16]:.2f} | "
                         f"{row[18]:.4f} |\n")
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")
    return 0 if output else 2


if __name__ == "__main__":
    raise SystemExit(main())
