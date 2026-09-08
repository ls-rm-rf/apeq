"""Exact finite-field target-rank audit. No floating-point rank or dimension proxy."""
from pathlib import Path
import csv, json, random
root = Path(__file__).resolve().parents[1]
out = root / 'experiments/bivariate-rank-v4'
out.mkdir(parents=True, exist_ok=True)
rng = random.Random(0x52414E4B)

def mul(a, b, p):
    c = [0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b): c[i+j] = (c[i+j] + x*y) % p
    return c

def rref(matrix, p):
    a = [row[:] for row in matrix]
    pivot = []; r = 0
    for c in range(len(a[0])):
        q = next((i for i in range(r, len(a)) if a[i][c]), None)
        if q is None: continue
        a[r], a[q] = a[q], a[r]
        z = pow(a[r][c], -1, p)
        a[r] = [(x*z) % p for x in a[r]]
        for i in range(len(a)):
            if i != r and a[i][c]:
                z = a[i][c]
                a[i] = [(x-z*y) % p for x, y in zip(a[i], a[r])]
        pivot.append(c); r += 1
        if r == len(a): break
    return a, pivot

rows = []
for p in [65537, 2**127-1]:
    for k in [4, 8]:
        for e in [1, 2, 3]:
            for tau in [0, 2]:
                D = e*k + 1 + tau
                N = (D+1)**2 // k + 1
                for trial in range(5):
                    S = [rng.randrange(p) for _ in range(k)] + [rng.randrange(1, p)]
                    powers = [[1]]
                    for j in range(e): powers.append(mul(powers[-1], S, p))
                    xs = rng.sample(range(1, 20000), N-D-1)
                    ys = [rng.randrange(p) for x in xs]
                    # T consists of the D+1 coefficients of R and all noisy replies.
                    target = [[1]+[0]*D+[1]*len(xs), S+[0]*(D+1-len(S))+ys]
                    masks = []
                    for j in range(e+1):
                        for d in range(1, D-j*k+1):
                            coeff = [0]*d + powers[j]
                            masks.append(coeff+[0]*(D+1-len(coeff)) +
                                [pow(x,d,p)*pow(y,j,p)%p for x,y in zip(xs,ys)])
                    B = [list(row) for row in zip(*masks)]
                    T = [list(row) for row in zip(*(target+masks))]
                    rank_b = len(rref(B,p)[1])
                    reduced, pivots = rref(T,p)
                    rank_t = len(pivots)
                    leakage = rank_t-rank_b
                    # Independently solve a sampled transcript and check whether
                    # both target coefficients are uniquely recovered despite free masks.
                    c = [rng.randrange(p), rng.randrange(1,p)]
                    h = [rng.randrange(p) for _ in masks]
                    z = [sum(x*y for x,y in zip(row,c+h))%p for row in T]
                    solved, pv = rref([row+[value] for row,value in zip(T,z)],p)
                    free = set(range(len(T[0]))) - set(pv)
                    recovered = all(j in pv and all(solved[pv.index(j)][f]==0 for f in free)
                                    and solved[pv.index(j)][-1]==c[j] for j in [0,1])
                    assert recovered == (leakage == 2)
                    # Reduced-view control: change P by y-beta and compensate
                    # h_0 by -(S-beta)/x. This preserves every coefficient of R.
                    alt_c = [(c[0]-S[0]) % p, (c[1]+1) % p]
                    alt_h = h[:]
                    for j in range(k): alt_h[j] = (alt_h[j]-S[j+1]) % p
                    alt_z = [sum(x*y for x,y in zip(row,alt_c+alt_h))%p for row in T]
                    assert alt_z[:D+1] == z[:D+1]
                    reduced_rank = len(rref(T[:D+1],p)[1])-len(rref(B[:D+1],p)[1])
                    assert reduced_rank == 1
                    rows.append(dict(field=str(p),k=k,e=e,tau=tau,D=D,N=N,trial=trial,
                        rank_B=rank_b,rank_T=rank_t,target_rank=leakage,
                        mask_nullity=len(masks)-rank_b,recovered=int(recovered),
                        reduced_target_rank=reduced_rank,alternative_R_match=1))
with (out/'trials.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
summary=dict(seed='0x52414E4B',trials=len(rows),full_target_recoveries=sum(r['recovered'] for r in rows),
    underdetermined_mask_trials=sum(r['mask_nullity']>0 for r in rows),
    reduced_view_controls=sum(r['alternative_R_match'] for r in rows),
    description='Affine P; exact modular Gaussian elimination; five random instances per parameter/field cell; no asymptotic claim')
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
