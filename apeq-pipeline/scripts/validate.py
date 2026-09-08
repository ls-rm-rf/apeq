#!/usr/bin/env python3
"""
validate.py -- enforce every invariant of the APEQ measurement specification.

Exits 0 if results.csv is publishable, non-zero otherwise. Run this before
make_tables.py or make_figures.py; both refuse to run on an invalid file.

Usage:
    python3 validate.py results.csv [--strict]
        [--allow-commit tree-REV ...]

--strict additionally fails on warnings (dirty git tree, high variance cells).
"""

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict

HEADER = [
    "run_id", "timestamp_utc", "git_commit", "hostname",
    "protocol", "backend", "variant",
    "batch_size", "input_bits", "field_bits", "security_param",
    "network", "rtt_ms", "bandwidth_mbps",
    "rep", "seed",
    "party",
    "setup_ms", "online_ms", "total_ms",
    "setup_bytes_sent", "setup_bytes_recv",
    "online_bytes_sent", "online_bytes_recv",
    "bytes_sent", "bytes_recv",
    "peak_rss_kb",
    "n_ot", "n_field_ops",
    "correct", "n_false_pos", "n_false_neg",
    "status", "note",
]

PROTOCOLS = {"apeq", "emp_eq", "aby_eq", "cryptflow2_eq", "volepsi_eq", "lu_eq"}
BACKENDS = {"ips_ole", "bit_ot", "ferret_vole", "n/a"}
VARIANTS = {"ole", "vole_hash", "yao", "gmw", "n/a"}
NETWORKS = {"lan", "wan", "round_sweep"}
PARTIES = {"A", "B"}
STATUSES = {"ok", "timeout", "oom", "crash", "skipped"}

# Framing overhead tolerated between a sender's counter and the peer's counter.
# The wrapper counts payload only, so in a correct implementation this is 0;
# a small allowance covers length prefixes if the wrapper is configured to count them.
FRAMING_SLACK_BYTES = 64

# Cells whose relative standard deviation exceeds this are flagged for review.
RSD_WARN = 0.20

OLE_DEFAULTS = {
    "ole_n": 1024,
    "ole_rho": 769,
    "ole_ell": 255,
    "ole_k": 128,
    "ole_t": 48,
}


def ole_params_from_note(row):
    """Read the structured OLE parameters appended to an APEQ result note.

    Historical rows predate these tags and therefore use the audited defaults.
    The caller receives the set of explicitly tagged fields so partial tags can
    be rejected during validation.
    """
    params = dict(OLE_DEFAULTS)
    present = set()
    malformed = []
    for token in (row.get("note") or "").split():
        key, sep, value = token.partition("=")
        if not sep or key not in OLE_DEFAULTS:
            continue
        present.add(key)
        try:
            params[key] = int(value)
        except ValueError:
            malformed.append(token)
    return params, present, malformed


# ----------------------------------------------------------------------------
# Independent lower bound on communication, computed from the protocol
# description rather than from the measurement. This is the check that catches
# a byte counter reporting fewer bytes than the message structure requires.
# ----------------------------------------------------------------------------
def theoretical_min_bytes(row):
    """Lower bound on total (sent+recv) application payload for one execution.

    Deliberately conservative: any real implementation must exceed this. A
    measured value below it means the counter is wrong, not that the protocol
    is clever.
    """
    proto = row["protocol"]
    batch = row["batch_size"]
    fb = row["field_bits"]
    ib = row["input_bits"]

    if proto == "apeq":
        variant = row["variant"]
        if variant == "ole" and row["backend"] == "bit_ot":
            # Two field ciphertexts per chosen bit OT and one field correction.
            return batch * (2 * ib + 1) * math.ceil(fb / 8)
        if variant == "ole":
            # IPS encoding: receiver sends v in F^n, sender responds on n
            # positions, per group of t inputs. New rows record their parameters
            # in the note; historical rows use the audited default setting.
            params, _, malformed = ole_params_from_note(row)
            if malformed:
                return 0
            n, t = params["ole_n"], params["ole_t"]
            if n <= 0 or t <= 0:
                return 0
            groups = math.ceil(batch / t)
            elems = groups * n * 2
            return elems * math.ceil(fb / 8)
        elif variant == "vole_hash":
            # One VOLE correlation per comparison plus one lambda-bit digest.
            return batch * math.ceil(fb / 8) + batch * 16
        return 0

    if proto == "volepsi_eq":
        return batch * math.ceil(fb / 8)

    # Circuit-based baselines: at minimum one garbled/OT-derived item per input
    # bit per comparison. Far below what they actually send.
    if proto in ("emp_eq", "aby_eq", "cryptflow2_eq", "lu_eq"):
        return batch * ib // 8

    return 0


# ----------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def dump(self, strict):
        for w in self.warnings:
            print(f"WARN  {w}")
        for e in self.errors:
            print(f"ERROR {e}")
        n_e, n_w = len(self.errors), len(self.warnings)
        print(f"\n{n_e} error(s), {n_w} warning(s)")
        if n_e:
            print("FAILED -- results.csv is not publishable.")
            return 1
        if strict and n_w:
            print("FAILED (strict) -- warnings present.")
            return 1
        print("PASSED")
        return 0


INT_FIELDS = ["batch_size", "input_bits", "field_bits", "security_param", "rep",
              "setup_bytes_sent", "setup_bytes_recv",
              "online_bytes_sent", "online_bytes_recv",
              "bytes_sent", "bytes_recv", "peak_rss_kb", "n_ot", "n_field_ops",
              "n_false_pos", "n_false_neg"]
FLOAT_FIELDS = ["rtt_ms", "bandwidth_mbps", "setup_ms", "online_ms", "total_ms"]


def load(path, rep):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            rep.error("file is empty")
            return []
        if header != HEADER:
            missing = set(HEADER) - set(header)
            extra = set(header) - set(HEADER)
            rep.error(f"header mismatch; missing={sorted(missing)} extra={sorted(extra)}")
            if missing:
                return []
        idx = {name: header.index(name) for name in HEADER if name in header}
        rows = []
        for ln, raw in enumerate(reader, start=2):
            if not raw:
                continue
            if len(raw) != len(header):
                rep.error(f"line {ln}: {len(raw)} fields, expected {len(header)}")
                continue
            row = {name: raw[idx[name]] for name in idx}
            row["_line"] = ln
            # a comma in `note` would have shifted the columns; csv handles
            # quoting, but an unquoted comma is caught by the length check above
            for k in INT_FIELDS:
                v = row.get(k, "")
                try:
                    row[k] = int(v) if v != "" else None
                except ValueError:
                    rep.error(f"line {ln}: {k}={v!r} is not an integer")
                    row[k] = None
            for k in FLOAT_FIELDS:
                v = row.get(k, "")
                try:
                    row[k] = float(v) if v != "" else None
                except ValueError:
                    rep.error(f"line {ln}: {k}={v!r} is not a number")
                    row[k] = None
            c = row.get("correct", "").strip().lower()
            row["correct"] = {"true": True, "false": False, "1": True, "0": False}.get(c)
            rows.append(row)
    return rows


def check_enums(rows, rep):
    for r in rows:
        ln = r["_line"]
        for field, allowed in (("protocol", PROTOCOLS), ("backend", BACKENDS),
                               ("variant", VARIANTS), ("network", NETWORKS),
                               ("party", PARTIES), ("status", STATUSES)):
            if r[field] not in allowed:
                rep.error(f"line {ln}: {field}={r[field]!r} not in {sorted(allowed)}")
        if r["protocol"] == "aby_eq":
            if r["backend"] != "n/a" or r["variant"] not in {"yao", "gmw"}:
                rep.error(f"line {ln}: ABY rows require backend='n/a' and "
                          "variant='yao' or 'gmw'")
        elif r["protocol"] == "apeq":
            expected_backend = {"ole": {"ips_ole", "bit_ot"}, "vole_hash": {"ferret_vole"}}.get(
                r["variant"]
            )
            if expected_backend is None or r["backend"] not in expected_backend:
                rep.error(f"line {ln}: APEQ variant/backend must be "
                          "ole/ips_ole, ole/bit_ot or vole_hash/ferret_vole")
            if r["variant"] == "ole" and r["backend"] == "ips_ole":
                params, present, malformed = ole_params_from_note(r)
                if malformed:
                    rep.error(f"line {ln}: malformed OLE parameter tag(s): "
                              f"{', '.join(malformed)}")
                if present and present != set(OLE_DEFAULTS):
                    missing = sorted(set(OLE_DEFAULTS) - present)
                    rep.error(f"line {ln}: partial OLE parameter tags; missing "
                              f"{missing}")
                n = params["ole_n"]
                rho = params["ole_rho"]
                ell = params["ole_ell"]
                k = params["ole_k"]
                t = params["ole_t"]
                if min(n, rho, ell, k, t) <= 0:
                    rep.error(f"line {ln}: OLE parameters must all be positive")
                elif n != rho + ell or ell != 2 * k - 1:
                    rep.error(f"line {ln}: invalid OLE code dimensions "
                              f"(n={n}, rho={rho}, ell={ell}, k={k})")
                elif n % k != 0 or n // k <= 4 or t > k or t > ell // 4:
                    rep.error(f"line {ln}: unsupported OLE batching parameters "
                              f"(n={n}, ell={ell}, k={k}, t={t})")
        elif r["variant"] != "n/a":
            rep.error(f"line {ln}: {r['protocol']} requires variant='n/a'")
        if r["security_param"] not in (80, 128):
            rep.error(f"line {ln}: security_param={r['security_param']} "
                      "(the earlier version compared a 9-20 bit configuration "
                      "against 128-bit baselines; this field is mandatory)")
        if "," in (r["note"] or ""):
            rep.warn(f"line {ln}: note contains a comma")


def check_pairing(rows, rep):
    """Every run_id appears exactly twice, once per party, and the byte counters
    of the two parties mirror each other."""
    by_id = defaultdict(list)
    for r in rows:
        by_id[r["run_id"]].append(r)

    for rid, group in by_id.items():
        lines = [r["_line"] for r in group]
        if len(group) != 2:
            rep.error(f"run_id {rid}: {len(group)} row(s), expected 2 (lines {lines})")
            continue
        parties = sorted(r["party"] for r in group)
        if parties != ["A", "B"]:
            rep.error(f"run_id {rid}: parties {parties}, expected ['A','B'] (lines {lines})")
            continue

        a = next(r for r in group if r["party"] == "A")
        b = next(r for r in group if r["party"] == "B")

        for f in ("protocol", "backend", "variant", "batch_size", "input_bits",
                  "field_bits", "security_param", "network", "rtt_ms",
                  "bandwidth_mbps", "rep", "seed", "git_commit"):
            if a[f] != b[f]:
                rep.error(f"run_id {rid}: {f} differs between parties "
                          f"({a[f]!r} vs {b[f]!r})")

        if a["status"] != "ok" or b["status"] != "ok":
            continue

        if None in (a["bytes_sent"], b["bytes_recv"], b["bytes_sent"], a["bytes_recv"]):
            rep.error(f"run_id {rid}: missing byte counters on an ok run")
            continue

        d1 = abs(a["bytes_sent"] - b["bytes_recv"])
        d2 = abs(b["bytes_sent"] - a["bytes_recv"])
        if d1 > FRAMING_SLACK_BYTES:
            rep.error(f"run_id {rid}: A.bytes_sent={a['bytes_sent']} but "
                      f"B.bytes_recv={b['bytes_recv']} (diff {d1})")
        if d2 > FRAMING_SLACK_BYTES:
            rep.error(f"run_id {rid}: B.bytes_sent={b['bytes_sent']} but "
                      f"A.bytes_recv={a['bytes_recv']} (diff {d2})")

        for phase in ("setup", "online"):
            d1 = abs(a[f"{phase}_bytes_sent"] - b[f"{phase}_bytes_recv"])
            d2 = abs(b[f"{phase}_bytes_sent"] - a[f"{phase}_bytes_recv"])
            if d1 > FRAMING_SLACK_BYTES or d2 > FRAMING_SLACK_BYTES:
                rep.error(f"run_id {rid}: {phase} byte counters do not mirror "
                          f"between parties (diffs {d1} and {d2})")

        # A-side reporting convention
        if a["n_false_pos"] != -1 or a["n_false_neg"] != -1:
            rep.warn(f"run_id {rid}: party A should report -1 for false pos/neg")


def check_timing(rows, rep):
    for r in rows:
        if r["status"] != "ok":
            if r["total_ms"] is not None:
                rep.warn(f"line {r['_line']}: status={r['status']} but timing is "
                         "populated; non-ok runs must not carry substituted values")
            continue
        for f in ("setup_ms", "online_ms", "total_ms"):
            if r[f] is None:
                rep.error(f"line {r['_line']}: {f} missing on an ok run")
                break
            if r[f] < 0:
                rep.error(f"line {r['_line']}: {f}={r[f]} is negative")
        else:
            if abs(r["total_ms"] - (r["setup_ms"] + r["online_ms"])) > 1.0:
                rep.error(f"line {r['_line']}: total_ms={r['total_ms']} != "
                          f"setup_ms+online_ms={r['setup_ms'] + r['online_ms']}")


def check_byte_accounting(rows, rep):
    for r in rows:
        if r["status"] != "ok":
            continue
        fields = ("setup_bytes_sent", "setup_bytes_recv", "online_bytes_sent",
                  "online_bytes_recv", "bytes_sent", "bytes_recv")
        if any(r[field] is None for field in fields):
            rep.error(f"line {r['_line']}: phase byte accounting is incomplete")
            continue
        if r["setup_bytes_sent"] + r["online_bytes_sent"] != r["bytes_sent"]:
            rep.error(f"line {r['_line']}: sent bytes do not equal setup+online")
        if r["setup_bytes_recv"] + r["online_bytes_recv"] != r["bytes_recv"]:
            rep.error(f"line {r['_line']}: received bytes do not equal setup+online")


def check_comm_lower_bound(rows, rep):
    """The check that catches a counter reporting 67 bits per comparison."""
    by_id = defaultdict(list)
    for r in rows:
        if r["status"] == "ok":
            by_id[r["run_id"]].append(r)
    for rid, group in by_id.items():
        if len(group) != 2:
            continue
        b = next((r for r in group if r["party"] == "B"), None)
        if b is None or b["bytes_sent"] is None or b["bytes_recv"] is None:
            continue
        total = b["bytes_sent"] + b["bytes_recv"]
        lo = theoretical_min_bytes(b)
        if lo and total < lo:
            per = total / b["batch_size"] if b["batch_size"] else 0
            rep.error(
                f"run_id {rid}: total payload {total} B is below the structural "
                f"minimum {lo} B for {b['protocol']}/{b['variant']} at batch "
                f"{b['batch_size']} ({per:.2f} B per comparison). The counter is wrong."
            )


def check_monotone_comm(rows, rep):
    """Communication cannot decrease as the batch grows; a decrease means the
    counter was reset mid-run."""
    cells = defaultdict(list)
    for r in rows:
        if r["status"] != "ok" or r["party"] != "B":
            continue
        if r["bytes_sent"] is None:
            continue
        key = (r["protocol"], r["backend"], r["variant"], r["input_bits"],
               r["field_bits"], r["network"], r["rtt_ms"],
               r["bandwidth_mbps"], r["security_param"])
        cells[key].append((r["batch_size"], r["bytes_sent"] + r["bytes_recv"], r["_line"]))

    for key, pts in cells.items():
        agg = defaultdict(list)
        for bs, tot, ln in pts:
            agg[bs].append(tot)
        means = sorted((bs, sum(v) / len(v)) for bs, v in agg.items())
        for (bs1, m1), (bs2, m2) in zip(means, means[1:]):
            if m2 < m1 * 0.999:
                rep.error(f"{key}: total bytes fall from {m1:.0f} at batch {bs1} "
                          f"to {m2:.0f} at batch {bs2}")


def check_duplicates(rows, rep):
    seen = Counter()
    for r in rows:
        key = (r["protocol"], r["backend"], r["variant"], r["batch_size"],
               r["input_bits"], r["field_bits"], r["network"], r["rtt_ms"],
               r["bandwidth_mbps"], r["security_param"], r["rep"], r["party"])
        seen[key] += 1
    for key, c in seen.items():
        if c > 1:
            rep.error(f"duplicate configuration repeated {c} times: {key}")


def check_identical_rows(rows, rep):
    """Two different batch sizes cannot cost exactly the same. This is the
    signature of a copy-paste error in a hand-built table."""
    by_cfg = defaultdict(dict)
    for r in rows:
        if r["status"] != "ok" or r["total_ms"] is None:
            continue
        key = (r["protocol"], r["backend"], r["variant"], r["input_bits"], r["network"],
               r["rtt_ms"], r["bandwidth_mbps"], r["party"])
        by_cfg[key].setdefault(r["batch_size"], []).append(r["total_ms"])

    for key, per_batch in by_cfg.items():
        items = sorted(per_batch.items())
        for (b1, v1), (b2, v2) in zip(items, items[1:]):
            if len(v1) == len(v2) and v1 and sorted(v1) == sorted(v2):
                rep.error(f"{key}: batch {b1} and batch {b2} have byte-identical "
                          "timing across all repetitions -- almost certainly a "
                          "duplicated row")


def check_correctness(rows, rep):
    for r in rows:
        if r["status"] != "ok" or r["party"] != "B":
            continue
        if r["correct"] is None:
            rep.error(f"line {r['_line']}: correct is missing on an ok run")
            continue
        if not r["correct"]:
            rep.error(f"line {r['_line']}: correctness failure "
                      f"({r['protocol']}/{r['variant']}, batch {r['batch_size']}, "
                      f"{r['input_bits']} bits, fp={r['n_false_pos']} fn={r['n_false_neg']})")
        # Theorem 5.1: the OLE variant has perfect correctness.
        if r["protocol"] == "apeq" and r["variant"] == "ole":
            if (r["n_false_pos"] or 0) > 0 or (r["n_false_neg"] or 0) > 0:
                rep.error(f"line {r['_line']}: apeq/ole reported "
                          f"fp={r['n_false_pos']} fn={r['n_false_neg']}; Theorem 5.1 "
                          "claims perfect correctness, so this is a bug in the "
                          "implementation or a defect in the theorem")


def check_provenance(rows, rep, allowed_commits=None):
    commits = {r["git_commit"] for r in rows if r["status"] == "ok"}
    if allowed_commits is None:
        if len(commits) > 1:
            rep.error(f"ok rows span multiple commits: {sorted(commits)}")
    elif commits != allowed_commits:
        rep.error(
            "ok-row provenance does not exactly match the explicitly allowed "
            f"commit set: actual={sorted(commits)} allowed={sorted(allowed_commits)}"
        )
    if "unknown" in commits or "" in commits:
        rep.error("ok rows have unknown source provenance; build images with "
                  "build_image.sh so one tree-<sha256> revision is injected")
    for c in commits:
        if c.endswith("-dirty"):
            rep.warn(f"commit {c} was built from a dirty tree; excluded from publication")

    sec = {r["security_param"] for r in rows if r["status"] == "ok"}
    if len(sec) > 1:
        rep.warn(f"dataset mixes security parameters {sorted(sec)}; make sure no "
                 "table compares across them")


def check_variance(rows, rep):
    cells = defaultdict(list)
    for r in rows:
        if r["status"] != "ok" or r["total_ms"] is None:
            continue
        key = (r["protocol"], r["backend"], r["variant"], r["batch_size"], r["input_bits"],
               r["network"], r["rtt_ms"], r["bandwidth_mbps"], r["party"])
        cells[key].append(r["total_ms"])
    for key, vals in cells.items():
        if len(vals) < 2:
            rep.warn(f"{key}: only {len(vals)} repetition(s); the spec asks for 10")
            continue
        mean = sum(vals) / len(vals)
        if mean <= 0:
            continue
        var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        rsd = math.sqrt(var) / mean
        if rsd > RSD_WARN:
            rep.warn(f"{key}: relative std dev {rsd:.1%} exceeds {RSD_WARN:.0%}")


def summarise(rows):
    ok = sum(1 for r in rows if r["status"] == "ok")
    by_status = Counter(r["status"] for r in rows)
    print(f"rows: {len(rows)}  ok: {ok}")
    for s, c in sorted(by_status.items()):
        if s != "ok":
            print(f"  {s}: {c}")
    runs = len({r["run_id"] for r in rows})
    print(f"executions: {runs}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="results.csv")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument(
        "--allow-commit",
        action="append",
        default=None,
        help=("allow an explicitly named source revision in a deliberately "
              "composed dataset; repeat once per required revision"),
    )
    args = ap.parse_args()

    rep = Report()
    rows = load(args.csv, rep)
    if not rows:
        return rep.dump(args.strict)

    summarise(rows)
    print()

    for fn in (check_enums, check_pairing, check_timing, check_byte_accounting,
               check_comm_lower_bound,
               check_monotone_comm, check_duplicates, check_identical_rows,
               check_correctness):
        fn(rows, rep)
    check_provenance(
        rows,
        rep,
        set(args.allow_commit) if args.allow_commit is not None else None,
    )
    check_variance(rows, rep)

    return rep.dump(args.strict)


if __name__ == "__main__":
    sys.exit(main())
