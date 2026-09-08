#!/usr/bin/env python3
"""
make_figures.py -- generate figures from results.csv.

Design rules, all of them consequences of defects in the previous version:

  * Logarithmic y-axis always. On a linear axis every protocol except the
    slowest collapses into an indistinguishable band at zero.
  * Logarithmic x-axis for batch sweeps.
  * Never average across batch sizes. Such an average is dominated entirely by
    the largest batch and carries no information.
  * Timeouts are annotated, not averaged over and not silently dropped.
  * Legend labels come from the CSV enum, so they cannot drift out of sync with
    the manuscript's citation numbering.

Usage:
    python3 make_figures.py results.csv --outdir figures/
"""

import argparse
import math
import os
import subprocess
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import LogLocator

import validate as V

DISPLAY = {
    ("apeq", "ole"): "APEQ (OLE)",
    ("apeq", "vole_hash"): "APEQ (VOLE)",
    ("lu_eq", "n/a"): "Lu et al.",
    ("emp_eq", "n/a"): "EMP-Yao",
    ("aby_eq", "yao"): "ABY-Yao",
    ("aby_eq", "gmw"): "ABY-GMW",
    ("cryptflow2_eq", "n/a"): "CrypTFlow2",
    ("volepsi_eq", "n/a"): "VOLE-PSI",
}
ORDER = [("apeq", "ole"), ("apeq", "vole_hash"), ("lu_eq", "n/a"),
         ("emp_eq", "n/a"), ("aby_eq", "yao"), ("aby_eq", "gmw"),
         ("cryptflow2_eq", "n/a"), ("volepsi_eq", "n/a")]

STYLE = {
    ("apeq", "ole"):        dict(color="#1b4965", marker="o", lw=2.2, ls="-"),
    ("apeq", "vole_hash"):  dict(color="#5fa8d3", marker="s", lw=2.0, ls="-"),
    ("lu_eq", "n/a"):       dict(color="#6a4c93", marker="X", lw=1.8, ls="-."),
    ("emp_eq", "n/a"):      dict(color="#9e2a2b", marker="^", lw=1.6, ls="--"),
    ("aby_eq", "yao"):      dict(color="#e09f3e", marker="v", lw=1.6, ls="--"),
    ("aby_eq", "gmw"):      dict(color="#f4a261", marker="<", lw=1.4, ls=":"),
    ("cryptflow2_eq", "n/a"): dict(color="#540b0e", marker="D", lw=1.6, ls="-."),
    ("volepsi_eq", "n/a"):  dict(color="#335c67", marker="P", lw=1.6, ls=":"),
}

plt.rcParams.update({
    "font.size": 9,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.5,
    "figure.dpi": 200,
    "savefig.bbox": "tight",
})


def agg(rows, xfield, fixed, value, network):
    """series[(proto,variant)] -> sorted [(x, mean, sd, n_timeout)]"""
    buckets = defaultdict(lambda: defaultdict(list))
    touts = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if r["party"] != "B" or r["network"] != network:
            continue
        if any(r[k] != v for k, v in fixed.items()):
            continue
        key = (r["protocol"], r["variant"])
        x = r[xfield]
        if r["status"] == "timeout":
            touts[key][x] += 1
            continue
        if r["status"] != "ok":
            continue
        v = value(r)
        if v is not None:
            buckets[key][x].append(v)

    out = {}
    for key, per_x in buckets.items():
        pts = []
        for x, vals in sorted(per_x.items()):
            m = sum(vals) / len(vals)
            sd = (math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
                  if len(vals) > 1 else 0.0)
            pts.append((x, m, sd, touts[key].get(x, 0)))
        out[key] = pts
    return out, touts


def draw(series, touts, xlabel, ylabel, title, path, logx):
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    any_data = False
    for key in ORDER:
        if key not in series or not series[key]:
            continue
        any_data = True
        xs = [p[0] for p in series[key]]
        ys = [p[1] for p in series[key]]
        es = [p[2] for p in series[key]]
        st = STYLE[key]
        ax.errorbar(xs, ys, yerr=es, label=DISPLAY[key], markersize=4,
                    capsize=2, elinewidth=0.8, **st)

    if not any_data:
        plt.close(fig)
        return False

    ax.set_yscale("log")
    if logx:
        ax.set_xscale("log")
        ax.xaxis.set_major_locator(LogLocator(base=10))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9)
    ax.yaxis.set_major_locator(LogLocator(base=10, numticks=12))

    # annotate timeouts rather than dropping them
    marked = set()
    for key, per_x in touts.items():
        for x, n in per_x.items():
            if n and x not in marked:
                ax.annotate("timeout", xy=(x, ax.get_ylim()[1] * 0.6),
                            fontsize=6, rotation=90, ha="center",
                            color="#9e2a2b", alpha=0.8)
                marked.add(x)

    ax.legend(fontsize=7, framealpha=0.9, loc="best")
    fig.savefig(path)
    plt.close(fig)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="results.csv")
    ap.add_argument("--outdir", default="figures")
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--allow-commit", action="append", default=None,
                    help="repeat for each required revision in a composed dataset")
    ap.add_argument("--ref-batch", type=int, default=100,
                    help="batch used for input-width sweeps (default: 100)")
    ap.add_argument("--ref-bits", type=int, default=None,
                    help="input width used for batch sweeps (default: maximum)")
    ap.add_argument("--time-metric", choices=("online_ms", "total_ms"),
                    default="total_ms")
    args = ap.parse_args()

    if not args.skip_validate:
        command = [sys.executable,
                   os.path.join(os.path.dirname(__file__) or ".", "validate.py"),
                   args.csv]
        for commit in args.allow_commit or []:
            command.extend(["--allow-commit", commit])
        rc = subprocess.call(command)
        if rc != 0:
            print("make_figures: refusing to plot an invalid file", file=sys.stderr)
            return 1

    rep = V.Report()
    rows = [r for r in V.load(args.csv, rep) if r["status"] in ("ok", "timeout")]
    if not rows:
        print("no usable rows", file=sys.stderr)
        return 1

    os.makedirs(args.outdir, exist_ok=True)
    bits_list = sorted({r["input_bits"] for r in rows})
    ref_batch = args.ref_batch
    ref_bits = args.ref_bits if args.ref_bits is not None else max(bits_list)
    networks = sorted({r["network"] for r in rows if r["network"] != "round_sweep"})

    kib = lambda r: ((r["bytes_sent"] + r["bytes_recv"]) / 1024.0
                     if r["bytes_sent"] is not None else None)
    ms = lambda r: r[args.time_metric]
    time_label = "Total time (ms)" if args.time_metric == "total_ms" else "Online time (ms)"

    made = []
    for net in networks:
        # (a) time vs input width, batch fixed
        s, t = agg(rows, "input_bits", {"batch_size": ref_batch}, ms, net)
        p = os.path.join(args.outdir, f"fig_time_vs_bits_{net}.pdf")
        if draw(s, t, "Input width (bits)", time_label,
                f"{net.upper()}, batch = {ref_batch}", p, logx=False):
            made.append(p)

        # (b) time vs batch, width fixed
        s, t = agg(rows, "batch_size", {"input_bits": ref_bits}, ms, net)
        p = os.path.join(args.outdir, f"fig_time_vs_batch_{net}.pdf")
        if draw(s, t, "Batch size", time_label,
                f"{net.upper()}, {ref_bits}-bit inputs", p, logx=True):
            made.append(p)

        # (c) communication vs input width
        s, t = agg(rows, "input_bits", {"batch_size": ref_batch}, kib, net)
        p = os.path.join(args.outdir, f"fig_comm_vs_bits_{net}.pdf")
        if draw(s, t, "Input width (bits)", "Communication (KiB)",
                f"{net.upper()}, batch = {ref_batch}", p, logx=False):
            made.append(p)

        # (d) communication vs batch
        s, t = agg(rows, "batch_size", {"input_bits": ref_bits}, kib, net)
        p = os.path.join(args.outdir, f"fig_comm_vs_batch_{net}.pdf")
        if draw(s, t, "Batch size", "Communication (KiB)",
                f"{net.upper()}, {ref_bits}-bit inputs", p, logx=True):
            made.append(p)

    for p in made:
        print(f"wrote {p}")

    caption = os.path.join(args.outdir, "captions.txt")
    with open(caption, "w") as f:
        f.write("Every caption must state: network setting, security parameter,\n"
                "number of repetitions, and that error bars are one sample standard\n"
                "deviation. Timeout annotations mark configurations exceeding 300 s.\n")
    print(f"wrote {caption}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
