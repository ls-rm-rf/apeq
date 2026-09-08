#!/usr/bin/env python3
"""Reproduce Table ``tab:attack`` with deterministic finite-field trials."""

from __future__ import annotations

import random


P = (1 << 127) - 1
CASES = ((1, 63, 132), (2, 8, 36), (3, 5, 35), (5, 5, 53))
TRIALS = 20


def evaluate(coefficients: list[int], x: int) -> int:
    result = 0
    for coefficient in reversed(coefficients):
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


def solve_full_column_rank(matrix: list[list[int]], rhs: list[int]) -> tuple[int, list[int] | None]:
    rows = [[value % P for value in row] + [value % P]
            for row, value in zip(matrix, rhs)]
    columns = len(matrix[0])
    rank = 0
    pivots: list[int] = []
    for column in range(columns):
        pivot = next((row for row in range(rank, len(rows))
                      if rows[row][column] != 0), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        inverse = pow(rows[rank][column], P - 2, P)
        rows[rank] = [value * inverse % P for value in rows[rank]]
        for row in range(len(rows)):
            if row == rank or rows[row][column] == 0:
                continue
            factor = rows[row][column]
            rows[row] = [(left - factor * right) % P
                         for left, right in zip(rows[row], rows[rank])]
        pivots.append(column)
        rank += 1
        if rank == columns:
            break
    if rank != columns:
        return rank, None
    solution = [0] * columns
    for row, column in enumerate(pivots):
        solution[column] = rows[row][-1]
    return rank, solution


def trial(d_p: int, k: int, n_total: int, rng: random.Random) -> int:
    d_r = k * d_p
    n_genuine = d_r + 1
    xs = list(range(1, n_total + 1))
    genuine = set(rng.sample(range(n_total), n_genuine))

    p_coefficients = [rng.randrange(P) for _ in range(d_p + 1)]
    while p_coefficients[-1] == 0:
        p_coefficients[-1] = rng.randrange(P)
    beta = rng.randrange(P)
    s_coefficients = [beta] + [rng.randrange(P) for _ in range(k)]
    while s_coefficients[-1] == 0:
        s_coefficients[-1] = rng.randrange(P)
    mask_coefficients = [0] + [rng.randrange(P) for _ in range(d_r)]
    while mask_coefficients[-1] == 0:
        mask_coefficients[-1] = rng.randrange(P)

    sx = [evaluate(s_coefficients, x) for x in xs]
    ys = [sx[i] if i in genuine else rng.randrange(P) for i in range(n_total)]
    replies = [(evaluate(mask_coefficients, x) +
                evaluate(p_coefficients, y)) % P
               for x, y in zip(xs, ys)]

    genuine_indices = sorted(genuine)
    interpolation_xs = [xs[i] for i in genuine_indices]
    interpolation_ys = [replies[i] for i in genuine_indices]
    r_at_zero = lagrange_evaluate(interpolation_xs, interpolation_ys, 0)

    matrix: list[list[int]] = []
    rhs: list[int] = []
    for i in range(n_total):
        if i in genuine:
            continue
        r_at_x = lagrange_evaluate(interpolation_xs, interpolation_ys, xs[i])
        matrix.append([(pow(ys[i], power, P) - pow(sx[i], power, P)) % P
                       for power in range(1, d_p + 1)])
        rhs.append((replies[i] - r_at_x) % P)

    rank, recovered_tail = solve_full_column_rank(matrix, rhs)
    if recovered_tail is None:
        return rank
    recovered_constant = (r_at_zero - sum(
        coefficient * pow(beta, power, P)
        for power, coefficient in enumerate(recovered_tail, start=1))) % P
    recovered = [recovered_constant] + recovered_tail
    if recovered != p_coefficients:
        raise AssertionError("full-rank system did not recover the holder polynomial")
    return rank


def main() -> None:
    rng = random.Random(0x41504551)
    print("| d_P | k | N | noisy pts | unknowns | rank | recovered |")
    print("|---:|---:|---:|---:|---:|---:|---:|")
    for d_p, k, n_total in CASES:
        ranks = [trial(d_p, k, n_total, rng) for _ in range(TRIALS)]
        recovered = sum(rank == d_p for rank in ranks)
        if recovered != TRIALS:
            raise AssertionError(f"rank failure for case {(d_p, k, n_total)}")
        n_genuine = k * d_p + 1
        print(f"| {d_p} | {k} | {n_total} | {n_total - n_genuine} | "
              f"{d_p + 1} | {min(ranks)} | {recovered}/{TRIALS} |")


if __name__ == "__main__":
    main()
