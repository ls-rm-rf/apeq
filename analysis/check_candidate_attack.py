"""Small-field end-to-end attack check and full-size algebra checks (stdlib only).

The small-field decoder solves the GS interpolation system and extracts polynomial
roots recursively. Exhaustive enumeration is used only to test the root extractor.
This is a research diagnostic, not a cryptographic backend.
"""

import argparse
import itertools
import json
import math
import random
from pathlib import Path

from estimate_rs import gs_parameters


def trim(a):
    while len(a) > 1 and a[-1] == 0:
        a.pop()
    return a


def add(a, b, p):
    out = [0] * max(len(a), len(b))
    for poly in (a, b):
        for i, c in enumerate(poly):
            out[i] = (out[i] + c) % p
    return trim(out)


def mul(a, b, p):
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i + j] = (out[i + j] + x * y) % p
    return trim(out)


def value(a, x, p):
    v = 0
    for c in reversed(a):
        v = (v * x + c) % p
    return v


def divide(a, b, p):
    a = a.copy()
    out = [0] * max(1, len(a) - len(b) + 1)
    inv = pow(b[-1], -1, p)
    while a != [0] and len(a) >= len(b):
        shift = len(a) - len(b)
        c = a[-1] * inv % p
        out[shift] = c
        for j, v in enumerate(b):
            a[j + shift] = (a[j + shift] - c * v) % p
        trim(a)
    return trim(out), trim(a)


def vanish(xs, p):
    out = [1]
    for x in xs:
        out = mul(out, [-x % p, 1], p)
    return out


def interpolate(xs, ys, p):
    out = [0]
    for i, (x, y) in enumerate(zip(xs, ys)):
        basis = vanish(xs[:i] + xs[i + 1:], p)
        scale = y * pow(value(basis, x, p), -1, p) % p
        out = add(out, [c * scale % p for c in basis], p)
    return out


def null_vector(matrix, p):
    """Return a nonzero right-null vector using modular row elimination."""
    rows, cols = len(matrix), len(matrix[0])
    pivots = []
    rank = 0
    for col in range(cols):
        pivot = next((r for r in range(rank, rows) if matrix[r][col]), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        inv = pow(matrix[rank][col], -1, p)
        matrix[rank] = [c * inv % p for c in matrix[rank]]
        for r in range(rank + 1, rows):
            factor = matrix[r][col]
            if factor:
                matrix[r] = [(a - factor * b) % p
                             for a, b in zip(matrix[r], matrix[rank])]
        pivots.append(col)
        rank += 1
        if rank == rows:
            break
    free = next(c for c in range(cols) if c not in pivots)
    out = [0] * cols
    out[free] = 1
    for r, c in reversed(list(enumerate(pivots))):
        out[c] = -sum(matrix[r][j] * out[j] for j in range(c + 1, cols)) % p
    return out


def compose(q, h, p):
    powers = [[1]]
    for _ in range(max(j for _, j in q)):
        powers.append(mul(powers[-1], h, p))
    out = [0]
    for (i, j), c in q.items():
        out = add(out, [0] * i + [c * v % p for v in powers[j]], p)
    return out


def polynomial_roots(q, degree, p):
    roots = set()

    def recurse(current, prefix):
        shift = min(i for i, _ in current)
        current = {(i - shift, j): c for (i, j), c in current.items()}
        for c in range(p):
            if sum(v * pow(c, j, p) for (i, j), v in current.items() if i == 0) % p:
                continue
            candidate = prefix + [c]
            if len(candidate) == degree + 1:
                if compose(q, candidate, p) == [0]:
                    roots.add(tuple(trim(candidate)))
                continue
            # Substitute y = c + x*y and remove any common power of x on recursion.
            transformed = {}
            for (i, j), v in current.items():
                for a in range(j + 1):
                    key = (i + a, a)
                    transformed[key] = (transformed.get(key, 0) +
                                        v * math.comb(j, a) * pow(c, j - a, p)) % p
            recurse({ij: v for ij, v in transformed.items() if v}, candidate)

    recurse(q, [])
    return roots


def decode(xs, ys, degree, agreements, p):
    m, D, _, constraints = gs_parameters(len(xs), degree, agreements)
    terms = [(i, j) for j in range(D // degree + 1)
             for i in range(D - degree * j + 1)]
    matrix = []
    for x, y in zip(xs, ys):
        for u in range(m):
            for v in range(m - u):
                matrix.append([
                    (math.comb(i, u) * math.comb(j, v) *
                     pow(x, i - u, p) * pow(y, j - v, p)) % p
                    if i >= u and j >= v else 0 for i, j in terms])
    assert len(matrix) == constraints < len(terms)
    coefficients = null_vector(matrix, p)
    q = {ij: c for ij, c in zip(terms, coefficients) if c}
    return [list(h) for h in polynomial_roots(q, degree, p)
            if sum(value(h, x, p) == y for x, y in zip(xs, ys)) >= agreements]


def sample_encoding(k, n, t, p, rng):
    inputs = list(range(1, t + 1))
    points = list(range(k + 1, k + n + 1))
    message = [rng.randrange(p) for _ in inputs]
    C, Z = interpolate(inputs, message, p), vanish(inputs, p)
    P = add(C, mul(Z, [rng.randrange(p) for _ in range(k - t)], p), p)
    genuine = set(rng.sample(range(n), 2 * k - 1))
    encoded = [value(P, x, p) if j in genuine else rng.randrange(p)
               for j, x in enumerate(points)]
    return inputs, points, message, P, genuine, encoded


def reduce_candidate(inputs, points, message, encoded, guessed, p):
    C, Z = interpolate(inputs, message, p), vanish(inputs, p)
    transformed = [(v - value(C, x, p)) * pow(value(Z, x, p), -1, p) % p
                   for x, v in zip(points, encoded)]
    guessed = sorted(guessed)
    guessed_x = [points[j] for j in guessed]
    R = interpolate(guessed_x, [transformed[j] for j in guessed], p)
    G = vanish(guessed_x, p)
    remaining = [j for j in range(len(points)) if j not in guessed]
    xs = [points[j] for j in remaining]
    ys = [(transformed[j] - value(R, points[j], p)) *
          pow(value(G, points[j], p), -1, p) % p for j in remaining]
    return C, Z, R, G, remaining, xs, ys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outdir', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'results/security-analysis')
    args = parser.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20260907)
    # Root extraction is compared with an independent exhaustive oracle over F_5.
    for _ in range(20):
        h1, h2 = [[rng.randrange(5) for _ in range(3)] for _ in range(2)]
        product = mul(h1, h2, 5)
        total = add(h1, h2, 5)
        q = {(0, 2): 1}
        q.update({(i, 1): -c % 5 for i, c in enumerate(total) if c})
        q.update({(i, 0): c for i, c in enumerate(product) if c})
        expected = {tuple(trim(list(h))) for h in itertools.product(range(5), repeat=3)
                    if compose(q, list(h), 5) == [0]}
        assert polynomial_roots(q, 2, 5) == expected

    attempts = []
    negative_decodes = 0
    # The attack samples its guesses without access to the hidden genuine set.
    for k, n, t, r in [(4, 24, 1, 1), (8, 48, 3, 2)]:
        for _ in range(5):
            inputs, points, message, P, _, encoded = sample_encoding(k, n, t, 101, rng)
            found = False
            for trial in range(1, 201):
                guessed = rng.sample(range(n), r)
                C, Z, R, G, _, xs, ys = reduce_candidate(
                    inputs, points, message, encoded, guessed, 101)
                for H in decode(xs, ys, k - 1 - t - r, 2 * k - 1 - r, 101):
                    recovered = add(C, mul(Z, add(R, mul(G, H, 101), 101), 101), 101)
                    if sum(value(recovered, x, 101) == y for x, y in zip(points, encoded)) >= 2 * k - 1:
                        assert recovered == P
                        found = True
                        break
                if found:
                    attempts.append(dict(k=k, n=n, t=t, trials=trial))
                    break
            assert found, "toy attack did not find a valid polynomial within its cap"
            wrong = message.copy()
            wrong[0] = (wrong[0] + 1) % 101
            C, Z, R, G, _, xs, ys = reduce_candidate(inputs, points, wrong, encoded,
                                                    rng.sample(range(n), r), 101)
            for H in decode(xs, ys, k - 1 - t - r, 2 * k - 1 - r, 101):
                recovered = add(C, mul(Z, add(R, mul(G, H, 101), 101), 101), 101)
                assert sum(value(recovered, x, 101) == y for x, y in zip(points, encoded)) < 2 * k - 1
            negative_decodes += 1

    # Full-size algebra only: this explicitly supplies a genuine guess to test reduction.
    p = 2**127 - 1
    for _ in range(5):
        inputs, points, message, P, genuine, encoded = sample_encoding(128, 1024, 48, p, rng)
        guessed = rng.sample(sorted(genuine), 30)
        C, Z, R, G, remaining, xs, ys = reduce_candidate(inputs, points, message, encoded, guessed, p)
        Q, rem = divide(add(P, [-c % p for c in C], p), Z, p)
        assert rem == [0] and len(Q) <= 80
        H, rem = divide(add(Q, [-c % p for c in R], p), G, p)
        assert rem == [0] and len(H) <= 50
        assert all(value(H, x, p) == y for j, x, y in zip(remaining, xs, ys) if j in genuine)
        assert sum(j in genuine for j in remaining) == 225
        assert add(C, mul(Z, add(R, mul(G, H, p), p), p), p) == P

    report = dict(status="passed", seed=20260907, root_extractor_exhaustive_checks=20,
                  toy_attacks=attempts, wrong_candidate_toy_decodes=negative_decodes,
                  full_size_conditional_algebra_checks=5,
                  full_size_decoding_or_attack_run=False)
    (args.outdir / "attack-checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
