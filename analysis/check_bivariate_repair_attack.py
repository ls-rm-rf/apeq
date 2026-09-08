#!/usr/bin/env python3
"""Validate the affine recovery attack on a degree-one bivariate repair.

The experiment mirrors Theorem ``thm:bivar-affine`` in the TDSC manuscript.  It
uses only the querier's polynomial S, the genuine-position set, the public query
points, and the replies released by the stripped construction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import time
from pathlib import Path


P = (1 << 127) - 1
K_VALUES = (8, 32, 63)
TAU_VALUES = (0, 4)
TRIALS = 20


def trim(poly: list[int]) -> list[int]:
    result = [value % P for value in poly]
    while len(result) > 1 and result[-1] == 0:
        result.pop()
    return result


def add(left: list[int], right: list[int], sign: int = 1) -> list[int]:
    size = max(len(left), len(right))
    result = [0] * size
    for i in range(size):
        result[i] = ((left[i] if i < len(left) else 0)
                     + sign * (right[i] if i < len(right) else 0)) % P
    return trim(result)


def scale(poly: list[int], scalar: int) -> list[int]:
    return trim([(scalar * value) % P for value in poly])


def multiply(left: list[int], right: list[int]) -> list[int]:
    result = [0] * (len(left) + len(right) - 1)
    for i, a in enumerate(left):
        for j, b in enumerate(right):
            result[i + j] = (result[i + j] + a * b) % P
    return trim(result)


def evaluate(poly: list[int], x: int) -> int:
    result = 0
    for coefficient in reversed(poly):
        result = (result * x + coefficient) % P
    return result


def lagrange_evaluate(xs: list[int], ys: list[int], z: int) -> int:
    for x, y in zip(xs, ys):
        if z == x:
            return y
    result = 0
    for i, (xi, yi) in enumerate(zip(xs, ys)):
        numerator = 1
        denominator = 1
        for j, xj in enumerate(xs):
            if i == j:
                continue
            numerator = numerator * (z - xj) % P
            denominator = denominator * (xi - xj) % P
        result = (result + yi * numerator * pow(denominator, P - 2, P)) % P
    return result


def random_poly(rng: random.Random, degree: int, constant: int | None = None) -> list[int]:
    coefficients = [rng.randrange(P) for _ in range(degree + 1)]
    if constant is not None:
        coefficients[0] = constant
    if degree > 0:
        while coefficients[-1] == 0:
            coefficients[-1] = rng.randrange(P)
    return coefficients


def build_r(p_poly: list[int], s_poly: list[int], h0: list[int], h1: list[int]) -> list[int]:
    p_of_s = add([p_poly[0]], scale(s_poly, p_poly[1]))
    x_h = [0] + add(h0, multiply(h1, s_poly))
    return add(p_of_s, x_h)


def reply(p_poly: list[int], h0: list[int], h1: list[int], x: int, y: int) -> int:
    return (evaluate(p_poly, y) + x *
            (evaluate(h0, x) + evaluate(h1, x) * y)) % P


def boundary_diagnostic(
    p_poly: list[int], s_poly: list[int], h0: list[int], h1: list[int],
    r_poly: list[int], selected_xs: list[int], selected_ys: list[int],
) -> bool:
    """Construct a second valid P from one fewer evaluation of F.

    This is a reduced-view algebra diagnostic, not a claim that the complete
    transcript is ambiguous when it contains additional usable noisy replies.
    """
    f_poly = [p_poly[1]] + h1
    vanishing = [1]
    for x in selected_xs:
        vanishing = multiply(vanishing, [(-x) % P, 1])
    f_alt = add(f_poly, scale(vanishing, 7))
    c1_alt = f_alt[0]
    if c1_alt == p_poly[1]:
        return False
    h1_alt = trim(f_alt[1:] or [0])
    beta = s_poly[0]
    c0_alt = (r_poly[0] - c1_alt * beta) % P
    p_alt = [c0_alt, c1_alt]
    p_alt_of_s = add([c0_alt], scale(s_poly, c1_alt))
    numerator = add(r_poly, p_alt_of_s, sign=-1)
    if numerator[0] != 0:
        return False
    quotient = trim(numerator[1:] or [0])
    h0_alt = add(quotient, multiply(h1_alt, s_poly), sign=-1)
    if len(h0_alt) - 1 > len(h0) - 1 or len(h1_alt) - 1 > len(h1) - 1:
        return False
    for x, y in zip(selected_xs, selected_ys):
        if reply(p_poly, h0, h1, x, y) != reply(p_alt, h0_alt, h1_alt, x, y):
            return False
    return build_r(p_alt, s_poly, h0_alt, h1_alt) == r_poly


def run_trial(k: int, tau: int, rng: random.Random) -> dict[str, float | int | bool]:
    d = k + 1 + tau
    n_genuine = d + 1
    n_total = math.floor((d + 1) ** 2 / k) + 1
    needed = d - k + 1
    xs = list(range(1, n_total + 1))
    genuine = set(rng.sample(range(n_total), n_genuine))

    p_poly = random_poly(rng, 1)
    s_poly = random_poly(rng, k, constant=rng.randrange(P))
    h0 = random_poly(rng, d - 1)
    h1 = random_poly(rng, d - 1 - k)
    r_poly = build_r(p_poly, s_poly, h0, h1)
    if len(r_poly) - 1 > d:
        raise AssertionError("constructed R exceeds its degree bound")

    sx = [evaluate(s_poly, x) for x in xs]
    ys = [sx[i] if i in genuine else rng.randrange(P) for i in range(n_total)]
    replies = [reply(p_poly, h0, h1, x, y) for x, y in zip(xs, ys)]
    usable = [i for i in range(n_total) if i not in genuine and ys[i] != sx[i]]

    start = time.perf_counter_ns()
    if len(usable) < needed:
        return dict(recovered=False, usable=len(usable), needed=needed,
                    attack_ns=time.perf_counter_ns() - start,
                    boundary_ok=False, n_total=n_total, n_genuine=n_genuine)
    chosen = usable[:needed]
    f_xs = [xs[i] for i in chosen]
    f_ys = [((replies[i] - evaluate(r_poly, xs[i])) *
             pow((ys[i] - sx[i]) % P, P - 2, P)) % P for i in chosen]
    c1 = lagrange_evaluate(f_xs, f_ys, 0)
    c0 = (r_poly[0] - c1 * s_poly[0]) % P
    recovered = [c0, c1] == p_poly
    attack_ns = time.perf_counter_ns() - start

    reduced = chosen[:-1]
    boundary_ok = boundary_diagnostic(
        p_poly, s_poly, h0, h1, r_poly,
        [xs[i] for i in reduced], [ys[i] for i in reduced],
    )
    return dict(recovered=recovered, usable=len(usable), needed=needed,
                attack_ns=attack_ns, boundary_ok=boundary_ok,
                n_total=n_total, n_genuine=n_genuine)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    rng = random.Random(0x42565231)
    rows: list[dict[str, object]] = []
    for k in K_VALUES:
        for tau in TAU_VALUES:
            trials = [run_trial(k, tau, rng) for _ in range(TRIALS)]
            recovered = sum(bool(item["recovered"]) for item in trials)
            boundary = sum(bool(item["boundary_ok"]) for item in trials)
            if recovered != TRIALS or boundary != TRIALS:
                raise AssertionError(f"attack validation failed for k={k}, tau={tau}")
            rows.append({
                "k": k,
                "tau": tau,
                "D": k + 1 + tau,
                "N": trials[0]["n_total"],
                "genuine_points": trials[0]["n_genuine"],
                "noisy_points": int(trials[0]["n_total"]) - int(trials[0]["n_genuine"]),
                "needed_points": trials[0]["needed"],
                "min_usable_points": min(int(item["usable"]) for item in trials),
                "recovered": recovered,
                "trials": TRIALS,
                "boundary_diagnostics": boundary,
                "mean_attack_us": round(statistics.mean(
                    int(item["attack_ns"]) for item in trials) / 1000, 3),
            })

    payload = {
        "field": "2^127-1",
        "seed": "0x42565231",
        "interpretation": (
            "Implementation validation of the affine recovery theorem; "
            "the reduced-view boundary diagnostic is not a complete-transcript attack."),
        "rows": rows,
    }
    print(json.dumps(payload, indent=2))
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "bivariate-repair-attack.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        with (args.output_dir / "bivariate-repair-attack.csv").open(
                "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
