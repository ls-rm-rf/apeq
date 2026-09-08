#!/usr/bin/env python3
"""Summarize non-perturbing APEQ-VOLE setup API decomposition."""

import argparse
import csv
import math
import re
from collections import defaultdict


FIELDS = (
    "base_ot_ms", "base_ot_sent", "base_ot_recv",
    "silent_vole_ms", "silent_vole_sent", "silent_vole_recv",
)


def fit(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    xm = sum(xs) / len(xs)
    ym = sum(ys) / len(ys)
    sxx = sum((x - xm) ** 2 for x in xs)
    slope = sum((x - xm) * (y - ym) for x, y in points) / sxx
    intercept = ym - slope * xm
    residual = sum((y - intercept - slope * x) ** 2 for x, y in points)
    total = sum((y - ym) ** 2 for y in ys)
    r2 = 1.0 if total == 0 else 1.0 - residual / total
    return slope, intercept, r2


def mean(values):
    return sum(values) / len(values)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--out-prefix", default="formal-vole-setup-decomposition")
    args = parser.parse_args()

    with open(args.csv, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    parsed = []
    for row in rows:
        if row["protocol"] != "apeq" or row["variant"] != "vole_hash":
            continue
        values = {}
        for field in FIELDS:
            match = re.search(rf"(?:^| ){field}=([0-9.]+)(?: |$)", row["note"])
            if not match:
                raise RuntimeError(f"{row['run_id']}/{row['party']}: missing {field}")
            values[field] = float(match.group(1))
        parsed.append({**row, **values})

    by_cell = defaultdict(list)
    by_run = defaultdict(dict)
    for row in parsed:
        by_cell[(float(row["rtt_ms"]), row["party"])].append(row)
        by_run[row["run_id"]][row["party"]] = row

    summary = []
    for (rtt, party), values in sorted(by_cell.items()):
        summary.append({
            "rtt_ms": rtt,
            "party": party,
            "n_runs": len(values),
            "base_ot_ms_mean": mean([v["base_ot_ms"] for v in values]),
            "silent_vole_ms_mean": mean([v["silent_vole_ms"] for v in values]),
            "setup_ms_mean": mean([float(v["setup_ms"]) for v in values]),
            "base_ot_sent_mean": mean([v["base_ot_sent"] for v in values]),
            "silent_vole_sent_mean": mean([v["silent_vole_sent"] for v in values]),
        })

    paired = defaultdict(list)
    for run_id, pair in by_run.items():
        if set(pair) != {"A", "B"}:
            raise RuntimeError(f"{run_id}: incomplete A/B pair")
        rtt = float(pair["A"]["rtt_ms"])
        base_sender_bytes = pair["A"]["base_ot_sent"] + pair["B"]["base_ot_sent"]
        vole_sender_bytes = pair["A"]["silent_vole_sent"] + pair["B"]["silent_vole_sent"]
        total_sender_bytes = int(pair["A"]["setup_bytes_sent"]) + int(pair["B"]["setup_bytes_sent"])
        if round(base_sender_bytes + vole_sender_bytes) != total_sender_bytes:
            raise RuntimeError(f"{run_id}: sender-attributed setup bytes do not add up")
        critical_setup = max(float(pair[p]["setup_ms"]) for p in ("A", "B"))
        separate_maxima = (
            max(pair[p]["base_ot_ms"] for p in ("A", "B")) +
            max(pair[p]["silent_vole_ms"] for p in ("A", "B"))
        )
        paired[rtt].append({
            "base_sender_bytes": base_sender_bytes,
            "vole_sender_bytes": vole_sender_bytes,
            "total_sender_bytes": total_sender_bytes,
            "critical_setup_ms": critical_setup,
            "separate_maxima_ms": separate_maxima,
        })

    pair_summary = []
    for rtt, values in sorted(paired.items()):
        pair_summary.append({
            "rtt_ms": rtt,
            "n_runs": len(values),
            "base_ot_total_sent_mean": mean([v["base_sender_bytes"] for v in values]),
            "silent_vole_total_sent_mean": mean([v["vole_sender_bytes"] for v in values]),
            "setup_total_sent_mean": mean([v["total_sender_bytes"] for v in values]),
            "critical_setup_ms_mean": mean([v["critical_setup_ms"] for v in values]),
            "separate_maxima_ms_mean": mean([v["separate_maxima_ms"] for v in values]),
        })

    fits = []
    for party in ("A", "B"):
        cells = [row for row in summary if row["party"] == party]
        for metric in ("base_ot_ms_mean", "silent_vole_ms_mean", "setup_ms_mean"):
            slope, intercept, r2 = fit([(row["rtt_ms"], row[metric]) for row in cells])
            fits.append({
                "party": party,
                "metric": metric.removesuffix("_mean"),
                "effective_rtts": slope,
                "intercept_ms": intercept,
                "r2": r2,
            })

    summary_path = args.out_prefix + "-party.csv"
    pair_path = args.out_prefix + "-sender-bytes.csv"
    fits_path = args.out_prefix + "-fits.csv"
    report_path = args.out_prefix + ".md"
    for path, values in ((summary_path, summary), (pair_path, pair_summary),
                         (fits_path, fits)):
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)

    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("# E5 APEQ-VOLE setup decomposition\n\n")
        handle.write("Configuration: batch=100, 64-bit inputs, 0.5/20/40/80 ms RTT, 10 independent sessions per RTT, revision `tree-b1174342219d`.\n\n")
        handle.write("No synchronization barrier was inserted between libOTe API calls. This preserves the measured protocol but permits one party to enter silent VOLE while its peer is still returning from base-OT bootstrap. Therefore local API durations are reported per party and **max(base)+max(VOLE) must not be treated as additive critical-path time**. Communication is reconstructed by sender attribution, which is exact and additive.\n\n")
        handle.write("## Sender-attributed setup communication\n\n")
        handle.write("| RTT (ms) | Runs | Base-OT bootstrap bytes | Silent-VOLE bytes | Total setup bytes | Base share |\n")
        handle.write("|---:|---:|---:|---:|---:|---:|\n")
        for row in pair_summary:
            share = row["base_ot_total_sent_mean"] / row["setup_total_sent_mean"]
            handle.write(
                f"| {row['rtt_ms']:g} | {row['n_runs']} | "
                f"{row['base_ot_total_sent_mean']:.0f} | "
                f"{row['silent_vole_total_sent_mean']:.0f} | "
                f"{row['setup_total_sent_mean']:.0f} | {share:.1%} |\n"
            )
        handle.write("\n## Local API-call timing\n\n")
        handle.write("| RTT (ms) | Party | Runs | Base-OT ms | Silent-VOLE ms | Local setup ms |\n")
        handle.write("|---:|---:|---:|---:|---:|---:|\n")
        for row in summary:
            handle.write(
                f"| {row['rtt_ms']:g} | {row['party']} | {row['n_runs']} | "
                f"{row['base_ot_ms_mean']:.3f} | {row['silent_vole_ms_mean']:.3f} | "
                f"{row['setup_ms_mean']:.3f} |\n"
            )
        handle.write("\n## RTT sensitivity of local calls\n\n")
        handle.write("| Party | Metric | Effective RTTs | R² |\n")
        handle.write("|---:|---|---:|---:|\n")
        for row in fits:
            handle.write(
                f"| {row['party']} | {row['metric']} | "
                f"{row['effective_rtts']:.3f} | {row['r2']:.5f} |\n"
            )

    print(f"wrote {summary_path}")
    print(f"wrote {pair_path}")
    print(f"wrote {fits_path}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
