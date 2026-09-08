"""Reproduce a classical candidate-message attack assessment, not security certification.

Run with Python 3.10+. Only the standard library is required.
The n'^2 m^4 value is an interpolation cost proxy, not a timed decoder or AES work.
"""

import argparse
import csv
import json
import math
from pathlib import Path


def monomials(degree, weighted_degree):
    j = weighted_degree // degree
    return (j + 1) * (weighted_degree + 1) - degree * j * (j + 1) // 2


def gs_parameters(length, degree, agreements):
    if agreements * agreements <= length * degree:
        return None
    # Beyond this bound the quadratic lower bound on the monomial count suffices.
    limit = max(1, length * degree // (agreements * agreements - length * degree) + 2)
    for m in range(1, limit + 1):
        D = m * agreements - 1
        count = monomials(degree, D)
        constraints = length * m * (m + 1) // 2
        if count > constraints:
            return m, D, count, constraints
    raise AssertionError("multiplicity bound failed")


def guess_exponent(n, ell, genuine, noise=0):
    return sum(math.log2((n - i) / (ell - i)) for i in range(genuine)) + sum(
        math.log2((n - genuine - i) / (n - ell - i)) for i in range(noise)
    )


def attack_row(k, n, t, genuine, noise=0):
    ell = 2 * k - 1
    degree = k - 1 - t - genuine
    length, agreements = n - genuine - noise, ell - genuine
    params = gs_parameters(length, degree, agreements)
    if params is None:
        return None
    m, D, count, constraints = params
    guesses = guess_exponent(n, ell, genuine, noise)
    interpolation = 2 * math.log2(length) + 4 * math.log2(m)
    return dict(k=k, n=n, ell=ell, t=t, guessed_genuine=genuine,
                guessed_noise=noise, residual_length=length, residual_degree=degree,
                agreements=agreements, multiplicity=m, weighted_degree=D,
                monomials=count, constraints=constraints,
                log2_expected_trials=guesses,
                log2_interpolation_proxy_per_trial=interpolation,
                log2_expected_interpolation_proxy=guesses + interpolation)


def search(k, n, t, puncture=False):
    ell = 2 * k - 1
    best = None
    # Keep at least degree one; direct interpolation is assessed separately.
    for genuine in range(k - 1 - t):
        for noise in range(n - ell + 1 if puncture else 1):
            guesses = guess_exponent(n, ell, genuine, noise)
            if best and guesses >= best["log2_expected_interpolation_proxy"]:
                break
            row = attack_row(k, n, t, genuine, noise)
            if row and (best is None or row["log2_expected_interpolation_proxy"] <
                        best["log2_expected_interpolation_proxy"]):
                best = row
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'results/security-analysis')
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    # Exact arithmetic checks independently verify the probability and finite GS counts.
    exact = math.comb(255, 32) / math.comb(1024, 32)
    assert abs(-math.log2(exact) - guess_exponent(1024, 255, 32)) < 1e-11
    row32 = attack_row(128, 1024, 48, 32)
    assert row32["residual_degree"] == 47
    assert row32["multiplicity"] == 12
    assert (row32["monomials"], row32["constraints"]) == (77520, 77376)
    assert gs_parameters(1024, 79, 255) is None
    for degree in range(1, 8):
        for D in range(25):
            enumerated = sum(1 for i in range(D + 1) for j in range(D + 1)
                             if i + degree * j <= D)
            assert enumerated == monomials(degree, D)

    examples = [attack_row(128, 1024, 48, r) for r in (27, 30, 32, 36, 40)]
    scenarios = [(128, 1024, t) for t in (1, 16, 32, 48, 63)]
    scenarios += [(128, n, 48) for n in (1280, 1536, 2048)]
    scenarios += [(k, 8 * k, 3 * k // 8) for k in (160, 192, 256)]
    sensitivity = [search(*case) for case in scenarios]
    best = search(128, 1024, 48, puncture=True)
    false_positive_log2 = math.log2(math.comb(769, 128)) - 48 * 127
    report = dict(
        metric="classical expected trials and n_prime^2 * m^4 interpolation proxy",
        limitations=["Not a lower bound on attack cost or a certified bit-security level",
                     "No full-size decoding, root extraction, wall-clock or memory calibration",
                     "Proxy omits hidden constants, root extraction, and field-to-machine conversion",
                     "Sensitivity rows change assumed parameters; they are not measured protocols",
                     "Search is restricted to this guessing/list-decoding family"],
        parameters=dict(k=128, n=1024, ell=255, rho=769, t=48, p="2^127-1"),
        examples=examples, best_with_noise_puncturing=best,
        sensitivity_genuine_guesses_only=sensitivity,
        direct_interpolation_log2_trials=guess_exponent(1024, 255, 80),
        wrong_candidate_log2_union_bound_rounded=false_positive_log2,
        arithmetic_checks="passed")
    (args.outdir / "rs-estimates.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, rows in (("rs-examples.csv", examples), ("rs-sensitivity.csv", sensitivity)):
        with (args.outdir / name).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps({"best": best, "direct_interpolation_log2_trials":
                     report["direct_interpolation_log2_trials"],
                     "arithmetic_checks": "passed"}, indent=2))


if __name__ == "__main__":
    main()
