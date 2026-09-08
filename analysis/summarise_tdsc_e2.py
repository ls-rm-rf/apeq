#!/usr/bin/env python3
"""Summarise the focused TDSC E2 parameter and control measurements."""

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "reproduction" / "experiments" / "ole-parameter-sweep"
INPUTS = {
    "ole-current.csv": "OLE current",
    "ole-smaller-group.csv": "OLE t=32",
    "ole-longer-code.csv": "OLE n=1280",
    "controls-emp-lu.csv": None,
    "control-apeq-vole.csv": "APEQ-VOLE",
}
CONTROL_LABELS = {"emp_eq": "EMP-Yao", "lu_eq": "Lu et al."}


def mean_sd(values):
    values = list(values)
    return statistics.mean(values), statistics.stdev(values)


def load_rows():
    rows = []
    for filename, fixed_label in INPUTS.items():
        with (DATA_DIR / filename).open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["status"] != "ok" or row["party"] != "B":
                    continue
                row["series"] = fixed_label or CONTROL_LABELS[row["protocol"]]
                rows.append(row)
    return rows


def summarise(rows):
    cells = defaultdict(list)
    for row in rows:
        cells[(row["series"], row["network"], int(row["batch_size"]))].append(row)

    output = []
    for (series, network, batch), group in sorted(cells.items()):
        assert len(group) == 10, (series, network, batch, len(group))
        assert all(row["correct"].lower() == "true" for row in group)
        setup_mean, setup_sd = mean_sd(float(row["setup_ms"]) for row in group)
        online_mean, online_sd = mean_sd(float(row["online_ms"]) for row in group)
        total_mean, total_sd = mean_sd(float(row["total_ms"]) for row in group)
        payload_mean, payload_sd = mean_sd(
            int(row["bytes_sent"]) + int(row["bytes_recv"]) for row in group
        )
        first = group[0]
        t = None
        n = None
        if series.startswith("OLE"):
            tags = dict(token.split("=", 1) for token in first["note"].split() if "=" in token)
            n = int(tags["ole_n"])
            t = int(tags["ole_t"])
        output.append({
            "series": series,
            "network": network,
            "batch": batch,
            "repetitions": len(group),
            "ole_n": n,
            "ole_t": t,
            "groups": math.ceil(batch / t) if t else None,
            "utilisation": batch / (math.ceil(batch / t) * t) if t else None,
            "setup_mean_ms": setup_mean,
            "setup_sd_ms": setup_sd,
            "online_mean_ms": online_mean,
            "online_sd_ms": online_sd,
            "total_mean_ms": total_mean,
            "total_sd_ms": total_sd,
            "payload_mean_bytes": payload_mean,
            "payload_sd_bytes": payload_sd,
        })
    return output


def write_csv(rows, path):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows, path):
    lookup = {(r["series"], r["network"], r["batch"]): r for r in rows}
    series_order = ["OLE current", "OLE t=32", "OLE n=1280", "EMP-Yao", "Lu et al.", "APEQ-VOLE"]
    lines = [
        "# TDSC E2 summary",
        "",
        "Party B means over ten independent fresh sessions. Payload is application data sent plus received.",
        "",
        "| Network | Batch | " + " | ".join(series_order) + " |",
        "|---|---:|" + "---:|" * len(series_order),
    ]
    for network in ("lan", "wan"):
        for batch in (32, 48, 100, 400):
            values = []
            for series in series_order:
                row = lookup[(series, network, batch)]
                values.append(f"{row['total_mean_ms']:.1f} ms / {row['payload_mean_bytes']/1024:.1f} KiB")
            lines.append(f"| {network.upper()} | {batch} | " + " | ".join(values) + " |")

    lines += ["", "## Candidate OLE ratios relative to the current setting", "",
              "| Network | Batch | t=32 time | t=32 payload | n=1280 time | n=1280 payload |",
              "|---|---:|---:|---:|---:|---:|"]
    for network in ("lan", "wan"):
        for batch in (32, 48, 100, 400):
            current = lookup[("OLE current", network, batch)]
            small = lookup[("OLE t=32", network, batch)]
            long = lookup[("OLE n=1280", network, batch)]
            lines.append(
                f"| {network.upper()} | {batch} | "
                f"{small['total_mean_ms']/current['total_mean_ms']:.3f}x | "
                f"{small['payload_mean_bytes']/current['payload_mean_bytes']:.3f}x | "
                f"{long['total_mean_ms']/current['total_mean_ms']:.3f}x | "
                f"{long['payload_mean_bytes']/current['payload_mean_bytes']:.3f}x |"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    rows = summarise(load_rows())
    write_csv(rows, DATA_DIR / "tdsc-e2-summary.csv")
    (DATA_DIR / "tdsc-e2-summary.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )
    write_markdown(rows, DATA_DIR / "tdsc-e2-summary.md")
    print(f"wrote {len(rows)} validated summary cells")


if __name__ == "__main__":
    main()
