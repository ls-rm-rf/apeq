#!/usr/bin/env python3
"""
make_tables.py -- generate LaTeX tables from results.csv.

No number in the manuscript is ever typed by hand; every table is regenerated
from the measurement file. Refuses to run on a file that fails validate.py.

Usage:
    python3 make_tables.py results.csv --outdir tables/
"""

import argparse
import math
import os
import subprocess
import sys
from collections import defaultdict

import validate as V

# Display names. Keeping these here, keyed by the CSV enum, is what stops
# figure and table legends from drifting out of sync with the manuscript.
DISPLAY = {
    ("apeq", "ole"): r"APEQ (OLE)",
    ("apeq", "vole_hash"): r"APEQ (VOLE)",
    ("lu_eq", "n/a"): r"Lu et al.",
    ("emp_eq", "n/a"): r"EMP-Yao",
    ("aby_eq", "yao"): r"ABY-Yao",
    ("aby_eq", "gmw"): r"ABY-GMW",
    ("cryptflow2_eq", "n/a"): r"CrypTFlow2",
    ("volepsi_eq", "n/a"): r"VOLE-PSI",
}
ORDER = [("apeq", "ole"), ("apeq", "vole_hash"), ("lu_eq", "n/a"),
         ("emp_eq", "n/a"), ("aby_eq", "yao"), ("aby_eq", "gmw"),
         ("cryptflow2_eq", "n/a"), ("volepsi_eq", "n/a")]

TIMEOUT_MARK = r"\textemdash"


def mean_sd(vals):
    if not vals:
        return None, None
    m = sum(vals) / len(vals)
    if len(vals) < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return m, math.sqrt(var)


def fmt(m, sd, unit=""):
    """Format mean +/- sd with a sensible number of significant figures."""
    if m is None:
        return TIMEOUT_MARK
    if m >= 1000:
        return f"{m:,.0f}\\,$\\pm$\\,{sd:,.0f}"
    if m >= 10:
        return f"{m:.1f}\\,$\\pm$\\,{sd:.1f}"
    return f"{m:.2f}\\,$\\pm$\\,{sd:.2f}"


def collect(rows, value, party="B"):
    """cell[(proto,variant)][(batch,bits,net)] -> list of values"""
    out = defaultdict(lambda: defaultdict(list))
    timeouts = defaultdict(set)
    for r in rows:
        if r["party"] != party:
            continue
        key = (r["protocol"], r["variant"])
        cell = (r["batch_size"], r["input_bits"], r["network"])
        if r["status"] == "timeout":
            timeouts[key].add(cell)
            continue
        if r["status"] != "ok":
            continue
        v = value(r)
        if v is not None:
            out[key][cell].append(v)
    return out, timeouts


def table_time(rows, network, bits_list, batch_list, caption, label,
               metric="online_ms"):
    data, timeouts = collect(rows, lambda r: r[metric])

    lines = [r"\begingroup", r"\scriptsize", r"\setlength{\tabcolsep}{2pt}",
             r"\begin{longtable}{ll" + "r" * len(bits_list) + "}",
             f"\\caption{{{caption}}}",
             f"\\label{{{label}}}\\\\"]
    lines.append(r"\hline")
    header = ("Protocol & Batch & " +
              " & ".join(f"{b}\\,bit" for b in bits_list) + r" \\")
    lines.append(header)
    lines.append(r"\hline")
    lines += [r"\endfirsthead", r"\hline", header, r"\hline", r"\endhead"]

    for key in ORDER:
        if key not in data:
            continue
        name = DISPLAY[key]
        first = True
        for batch in batch_list:
            cells = []
            for bits in bits_list:
                c = (batch, bits, network)
                if c in timeouts[key] and not data[key].get(c):
                    cells.append(TIMEOUT_MARK)
                else:
                    m, sd = mean_sd(data[key].get(c, []))
                    cells.append(fmt(m, sd))
            label_col = name if first else ""
            lines.append(f"{label_col} & {batch} & " + " & ".join(cells) + r" \\")
            first = False
        lines.append(r"\hline")

    lines.append(r"\end{longtable}")
    lines.append(r"\endgroup")
    return "\n".join(lines)


def table_comm(rows, network, bits_list, batch_list, caption, label):
    def total_kb(r):
        if r["bytes_sent"] is None or r["bytes_recv"] is None:
            return None
        return (r["bytes_sent"] + r["bytes_recv"]) / 1024.0

    data, timeouts = collect(rows, total_kb)
    header = ("Protocol & Batch & " +
              " & ".join(f"{b}\\,bit" for b in bits_list) + r" \\")
    lines = [r"\begingroup", r"\scriptsize", r"\setlength{\tabcolsep}{2pt}",
             r"\begin{longtable}{ll" + "r" * len(bits_list) + "}",
             f"\\caption{{{caption}}}", f"\\label{{{label}}}\\\\",
             r"\hline", header, r"\hline", r"\endfirsthead",
             r"\hline", header, r"\hline", r"\endhead"]
    for key in ORDER:
        if key not in data:
            continue
        first = True
        for batch in batch_list:
            cells = []
            for bits in bits_list:
                c = (batch, bits, network)
                if c in timeouts[key] and not data[key].get(c):
                    cells.append(TIMEOUT_MARK)
                else:
                    m, sd = mean_sd(data[key].get(c, []))
                    cells.append(fmt(m, sd))
            lines.append(f"{DISPLAY[key] if first else ''} & {batch} & " +
                         " & ".join(cells) + r" \\")
            first = False
        lines.append(r"\hline")
    lines += [r"\end{longtable}", r"\endgroup"]
    return "\n".join(lines)


def table_amortised(rows, network, bits, batch_list, caption, label):
    """Per-comparison online time and total payload -- the table that supports the
    bit-width-independence claim."""
    t, _ = collect(rows, lambda r: r["online_ms"])
    c, _ = collect(rows, lambda r: (r["bytes_sent"] + r["bytes_recv"]) / 1024.0
                   if r["bytes_sent"] is not None else None)
    header = r"Protocol & Batch & Online $\mu$s/cmp & Total B/cmp \\"
    lines = [r"\begingroup", r"\small", r"\begin{longtable}{lrrr}",
             f"\\caption{{{caption}}}", f"\\label{{{label}}}\\\\",
             r"\hline", header, r"\hline", r"\endfirsthead",
             r"\hline", header, r"\hline", r"\endhead"]
    for key in ORDER:
        if key not in t:
            continue
        first = True
        for batch in batch_list:
            cell = (batch, bits, network)
            tm, _ = mean_sd(t[key].get(cell, []))
            cm, _ = mean_sd(c[key].get(cell, []))
            if tm is None:
                continue
            lines.append(f"{DISPLAY[key] if first else ''} & {batch} & "
                         f"{tm * 1000 / batch:,.1f} & {cm * 1024 / batch:,.0f} \\\\")
            first = False
        lines.append(r"\hline")
    lines += [r"\end{longtable}", r"\endgroup"]
    return "\n".join(lines)


def network_caption(rows, network):
    """Return a data-derived network label for table captions."""
    rtts = sorted({r["rtt_ms"] for r in rows if r["network"] == network})
    if len(rtts) == 1:
        return f"{network.upper()} ({rtts[0]:g}\\,ms RTT)"
    if rtts:
        values = ", ".join(f"{rtt:g}" for rtt in rtts)
        return f"{network.upper()} ({values}\\,ms RTT)"
    return network.upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="results.csv")
    ap.add_argument("--outdir", default="tables")
    ap.add_argument("--skip-validate", action="store_true",
                    help="for debugging only; never use for the submitted build")
    ap.add_argument("--allow-commit", action="append", default=None,
                    help="repeat for each required revision in a composed dataset")
    args = ap.parse_args()

    if not args.skip_validate:
        command = [sys.executable,
                   os.path.join(os.path.dirname(__file__) or ".", "validate.py"),
                   args.csv]
        for commit in args.allow_commit or []:
            command.extend(["--allow-commit", commit])
        rc = subprocess.call(command)
        if rc != 0:
            print("make_tables: refusing to generate tables from an invalid file",
                  file=sys.stderr)
            return 1

    rep = V.Report()
    rows = V.load(args.csv, rep)
    rows = [r for r in rows if r["status"] in ("ok", "timeout")]
    if not rows:
        print("no usable rows", file=sys.stderr)
        return 1

    bits_list = sorted({r["input_bits"] for r in rows})
    batch_list = sorted({r["batch_size"] for r in rows})
    sec = sorted({r["security_param"] for r in rows})[0]
    reps = max(len([1 for r in rows if r["party"] == "B"]), 1)

    os.makedirs(args.outdir, exist_ok=True)

    networks = sorted({r["network"] for r in rows})
    outputs = {}
    for network in networks:
        net_caption = network_caption(rows, network)
        common_note = (f"All protocols run at $\\kappa={sec}$. Values are Party B "
                       "mean\\,$\\pm$\\,sample standard deviation over independent "
                       f"repetitions; {TIMEOUT_MARK} marks a configuration that "
                       "exceeded the 300\\,s timeout.")
        outputs[f"tab_time_{network}.tex"] = table_time(
            rows, network, bits_list, batch_list,
            f"Online running time (ms), {net_caption}. {common_note} Setup is "
            f"reported separately in Table~\\ref{{tab:setup-{network}}}.",
            f"tab:time-{network}")
        outputs[f"tab_setup_{network}.tex"] = table_time(
            rows, network, bits_list, batch_list,
            f"Offline/setup running time (ms), {net_caption}. {common_note}",
            f"tab:setup-{network}", metric="setup_ms")
        outputs[f"tab_total_{network}.tex"] = table_time(
            rows, network, bits_list, batch_list,
            f"Total running time (ms), {net_caption}. {common_note}",
            f"tab:total-{network}", metric="total_ms")
        outputs[f"tab_comm_{network}.tex"] = table_comm(
            rows, network, bits_list, batch_list,
            f"Total communication (KiB), {net_caption}. {common_note} "
            "Counts are application-layer payload summed over both directions.",
            f"tab:comm-{network}")
        outputs[f"tab_amortised_{network}.tex"] = table_amortised(
            rows, network, max(bits_list), batch_list,
            f"Amortised online time and total communication per comparison at "
            f"{max(bits_list)}-bit inputs, "
            f"{net_caption}.", f"tab:amortised-{network}")

    for fname, body in outputs.items():
        path = os.path.join(args.outdir, fname)
        with open(path, "w") as f:
            f.write("% GENERATED BY make_tables.py -- DO NOT EDIT\n")
            f.write(f"% source: {args.csv}\n")
            f.write(body + "\n")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
