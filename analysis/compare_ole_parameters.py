"""Compare the paper's three IPS-OLE parameter sets under one attack family.

The reported exponent is an interpolation-cost proxy.  It is not a security
lower bound, a certified bit-security level, or a measured decoder runtime.
"""

import argparse
import csv
import json
from pathlib import Path

from estimate_rs import search


PARAMETERS = (
    ("current", 1024, 769, 255, 128, 48),
    ("smaller_group", 1024, 769, 255, 128, 32),
    ("longer_code", 1280, 1025, 255, 128, 48),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    rows = []
    for name, n, rho, ell, k, t in PARAMETERS:
        if n != rho + ell:
            raise AssertionError("n must equal rho + ell")
        best = search(k, n, t, puncture=True)
        rows.append({
            "config": name,
            "n": n,
            "rho": rho,
            "ell": ell,
            "k": k,
            "t": t,
            "guessed_genuine": best["guessed_genuine"],
            "guessed_noise": best["guessed_noise"],
            "multiplicity": best["multiplicity"],
            "log2_expected_trials": best["log2_expected_trials"],
            "log2_interpolation_proxy_per_trial":
                best["log2_interpolation_proxy_per_trial"],
            "log2_expected_interpolation_proxy":
                best["log2_expected_interpolation_proxy"],
        })

    report = {
        "metric": "classical expected trials times n_prime^2 * m^4 interpolation proxy",
        "scope": "guessing and Guruswami-Sudan list-decoding family with genuine and noise puncturing",
        "warning": "not a security lower bound or certified bit-security estimate",
        "rows": rows,
    }
    (args.outdir / "ole-parameter-attack-proxy.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with (args.outdir / "ole-parameter-attack-proxy.csv").open(
            "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
