"""Bounded independent audit of the V5 affine-target family lemma.

This is a proof diagnostic, not a cryptographic security experiment. No timing
claims. Build the coefficient map directly; compare its kernel with the proposed
quotient basis and check unique recovery from the entire exposed transcript.
"""
import json
import random
from pathlib import Path


def mul(a, b, p):
    out = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            out[i+j] = (out[i+j] + x*y) % p
    return out


def rank(a, p):
    a = [row[:] for row in a]
    r = 0
    for j in range(len(a[0])):
        q = next((i for i in range(r, len(a)) if a[i][j]), None)
        if q is None:
            continue
        a[q], a[r] = a[r], a[q]
        inv = pow(a[r][j], -1, p)
        a[r] = [x*inv % p for x in a[r]]
        for i in range(r+1, len(a)):
            z = a[i][j]
            if z:
                a[i] = [(x-z*y) % p for x, y in zip(a[i], a[r])]
        r += 1
        if r == len(a):
            break
    return r


def main():
    rng = random.Random(0x563546414D)
    records = []
    for p in (65537, 2**127-1):
        for e in range(1, 7):
            for k in (1, 2, 4):
                for tau in (0, 2):
                    D = e*k + 1 + tau
                    W = e*D - k*e*(e+1)//2 + 1
                    T = sum(j*(D-(j+1)*k) for j in range(1, e))
                    N = (D+1)**2//k + 1
                    assert N-D-1 >= W
                    assert ((D+1)**2 - k*(D+1+W) ==
                            e*(e-1)*k*k//2 + (e-1)*tau*k + 3*(e-1)*k + (tau+2)**2)
                    S = [rng.randrange(p) for _ in range(k)] + [rng.randrange(1, p)]
                    powers = [[1]]
                    for _ in range(e):
                        powers.append(mul(powers[-1], S, p))
                    # Q basis: 1,y, then x^a y^j with a>=1.
                    qb = [(0, 0), (0, 1)] + [(a, j) for j in range(e+1)
                                                            for a in range(1, D-j*k+1)]
                    jb = [(a, 0) for a in range(D-k+1)] + [
                        (a, j) for j in range(1, e) for a in range(1, D-(j+1)*k+1)]
                    assert len(jb) == W == len(qb)-(D+1)
                    R = [[0]*len(qb) for _ in range(D+1)]
                    for col, (a, j) in enumerate(qb):
                        for d, v in enumerate(powers[j]):
                            R[a+d][col] = v
                    assert rank(R, p) == D+1
                    # Each proposed (y-S)J basis vector is actually in ker R.
                    for a, j in jb:
                        v = [0]*len(qb)
                        v[qb.index((a, j+1))] = 1
                        for d, s in enumerate(S):
                            v[qb.index((a+d, j))] = (v[qb.index((a+d, j))]-s) % p
                        assert all(sum(x*y for x, y in zip(row, v)) % p == 0 for row in R)
                    xs = rng.sample(range(1, 20000), W)
                    ys = [rng.randrange(p) for _ in xs]
                    V = [[pow(x, a, p)*pow(y, j, p) % p for a, j in jb]
                         for x, y in zip(xs, ys)]
                    full = R + [[pow(x, a, p)*pow(y, j, p) % p for a, j in qb]
                                for x, y in zip(xs, ys)]
                    rank_v, rank_full = rank(V, p), rank(full, p)
                    # The deterministic implication is conditional on these events.
                    collisions = sum(y == sum(s*pow(x, d, p) for d, s in enumerate(S)) % p
                                     for x, y in zip(xs, ys))
                    if rank_v == W and collisions == 0:
                        assert rank_full == len(qb)
                    # Counter-control: taking only the genuine replies leaves one
                    # affine-target degree of freedom (not merely free masks).
                    assert rank([row[2:] for row in R], p) == D
                    records.append(dict(p=str(p), e=e, k=k, tau=tau, D=D, N=N,
                                        W=W, T=T, rank_V=rank_v, rank_full=rank_full,
                                        coefficients=len(qb), collisions=collisions))
    out = Path(__file__).resolve().parents[1]/'experiments/application-v5'
    out.mkdir(parents=True, exist_ok=True)
    summary = dict(cases=len(records), full_rank_cases=sum(r['rank_full']==r['coefficients']
                   for r in records), seed='0x563546414D', purpose='bounded proof diagnostic',
                   records=records)
    (out/'family-proof-check.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='records'}))


if __name__ == '__main__':
    main()
