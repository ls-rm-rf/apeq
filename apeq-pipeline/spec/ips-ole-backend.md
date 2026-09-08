# IPS Noisy-Encoding OLE Backend — Implementation Specification

Semi-honest batch OLE from noisy Reed–Solomon encodings, following Ishai–Prabhakaran–Sahai
[27] with the encoding presentation of Ghosh–Nielsen–Nilges [32, Fig. 2]. This is the
`ips_ole` backend of `apeq`.

Scope: **static semi-honest model only, conditional on the backend assumptions.**
The paper proves perfect equality reduction in the ideal OLE model; it does not
prove end-to-end UC security of this libOTe software composition. See
[security scope](../../SECURITY.md) for the concrete RS analysis and VOLE boundary.
A malicious extension would require consistency checks, coefficient constraints,
a new proof and new measurements; it is not provided here.

---

## 1. Parameters

Fixed at nominal `kappa = 128`. The Reed--Solomon instantiation in
Ishai--Prabhakaran--Sahai requires `n = c*k` with `c > 4` and identifies `c = 8`
as a safer choice. We therefore use:

```
n      = 1024       codeword length (c = 8)
rho    = 769        randomised positions
ell    = n - rho    = 255      non-noisy positions
k      = (ell-1)/2 + 1 = 128   message length / number of input points
deg_P  = k-1        = 127      receiver's interpolation polynomial
deg_A  = (ell-1)/2  = 127      sender's polynomial A
deg_B  = ell-1      = 254      sender's polynomial B
t      = 48         batch size (encoded inputs), t <= ell/4 = 63
```

`ell` **must be odd**. The derived values are not independent tuning knobs:
`k = (ell+1)/2`, `deg_P = k-1`, and therefore
`deg_A + deg_P = ell-1`; reconstruction needs exactly `ell` points. Assert
`n = rho+ell`, `n = c*k` for an integer `c > 4`, and all of these identities at
construction.

Field: default `p = 2^127 - 1`. This core accepts field elements in `[0,p)`; it does
**not** losslessly encode every 127- or 128-bit integer. Every `ell_in <= 126` bit
string does embed injectively as an integer in this field; 127 and 128 bits do not.
Exact 128-bit APEQ therefore
requires either a prime greater than `2^128-1` or a specified injective limb
decomposition. Truncation and hashing are not zero-error substitutes. Until that outer
encoding is specified, the cross-baseline publication matrix uses
8/16/24/32/48/64-bit inputs. The APEQ drivers additionally support and measure
80/96/120/126-bit inputs with an injective representation. All arithmetic uses a single
Montgomery-domain type `Fp`; see §4.

---

## 2. Interface

```cpp
struct OleParams { size_t n, rho, ell, k, t; };

class Retriever {
public:
  // Receiver-side OT interface. private_choices remain local and must not appear
  // in the network transcript.
  virtual std::vector<Fp> retrieve(
      size_t universe_size,
      const std::vector<size_t>& private_choices) = 0;
};

// Receiver side
class OleReceiver {
public:
  OleReceiver(OleParams, MasterSeed public_seed,
              MasterSeed receiver_private_seed, uint64_t session_id);
  // Round 1: encode inputs, produce the public part of the encoding.
  Encoding encode(const std::vector<Fp>& x);          // x.size() == t
  // Give choices to the local OT receiver; no offered sender values cross this API.
  std::vector<Fp> retrieve(Retriever&);
  // Round 2: given the ell values retrieved by OT, recover y_i = a_i*x_i + b_i.
  std::vector<Fp> reconstruct(const std::vector<Fp>& retrieved);
private:
  std::vector<size_t> L_;        // passed only to the local receiver-side Retriever.
  MasterSeed session_key_;
  uint64_t batch_counter_;
};

// Sender side
class OleSender {
public:
  OleSender(OleParams, MasterSeed public_seed,
            MasterSeed sender_private_seed, uint64_t session_id);
  // Given the public encoding, produce the n values to be offered in the OT.
  std::vector<Fp> respond(const Encoding&,
                          const std::vector<Fp>& a,   // a.size() == t
                          const std::vector<Fp>& b);  // b.size() == t
};
```

The `ell`-out-of-`n` retrieval is **not implemented in the core**. It is delegated to
the OT extension of EMP or libOTe behind a `Retriever` interface. The private choices
may be passed to that local receiver-side component, but they must never be serialized,
logged, returned by an accessor, or revealed to the sender. This is the single largest
saving in the build and the part most likely to contain subtle bugs if hand-rolled.

---

## 3. Algorithm

Public evaluation points `pts_in[1..k]` and `pts_out[1..n]`, derived
deterministically from a public seed (§6), known to both parties.

**Receiver, `encode(x)`:**
1. Sample `L ⊂ [n]`, `|L| = ell`, uniformly. **Fixed weight — see §5.**
2. Pick `u ∈ F_p^k` uniformly subject to `u_i = x_i` for `i in [t]`.
3. Let `P` be the unique degree-`k-1` polynomial with `P(pts_in_i) = u_i`; set
   `(Gu)_j = P(pts_out_j)` for `j in [n]`.
4. Pick `v ∈ F_p^n` uniformly subject to `v_j = (Gu)_j` for `j in L`.
5. Send `v`. (`G` is public, derived from the seed.)

**Sender, `respond(v, a, b)`:**
1. Pick `A` uniformly from the polynomials of degree at most `deg_A`, subject to
   `A(pts_in_i) = a_i` for `i in [t]`.
2. Pick `B` uniformly from the polynomials of degree at most `deg_B`, subject to
   `B(pts_in_i) = b_i` for `i in [t]`.
3. Return `w_j = A(pts_out_j) * v_j + B(pts_out_j)` for `j in [n]`.

`B` has degree `ell-1`, strictly greater than `deg_A`; this is what hides `A`, hence the
sender's inputs. Do not "optimise" `deg_B` downwards — it breaks privacy, not just the
proof.

**Receiver, `reconstruct(retrieved)`:**
1. For `j in L`, `w_j = A(pts_out_j)*P(pts_out_j) + B(pts_out_j) = Y(pts_out_j)` where
   `Y = A*P + B` has degree `ell-1`.
2. Interpolate `Y` from the `ell` points.
3. Output `y_i = Y(pts_in_i)` for `i in [t]`. Correctness:
   `Y(pts_in_i) = a_i*x_i + b_i`.

---

## 4. Field arithmetic

All arithmetic goes through one Montgomery-domain type. **No raw integer arithmetic on
field elements anywhere outside `Fp`.**

- `Fp` exposes `+ - * inv pow`, and conversion only at the I/O boundary.
- No implicit conversion from integers. Construction is explicit.
- Enable a debug build flag `FP_CHECKED` that asserts every value is in `[0, p)` on
  every operation. CI runs the whole test suite under it.

**Acceptance test F1.** For `10^6` random pairs, cross-validate `+ - * inv` against
Python's `int` arithmetic mod `p`. Zero mismatches.

**Acceptance test F2.** Grep the build for arithmetic on field-carrying types outside
`Fp`: `grep -rn 'uint64_t.*[*+-].*field' src/` must return nothing. Automate as a lint
step; this catches the class of bug where a value silently leaves the field.

---

## 5. Noise distribution — the highest-risk item

The assumption requires `L` chosen **uniformly among subsets of exact size `ell`**.
Bernoulli sampling gives `|L|` a binomial distribution and is **not** a valid
substitute: the security reduction uses `|R| = rho` as a deterministic fact, and the
list-decoding margin is computed for a fixed agreement count. A Bernoulli variant would
fluctuate across the Guruswami–Sudan threshold from run to run.

**Required implementation.** Partial Fisher–Yates over `[n]` using a CSPRNG, taking the
first `ell` entries:

```cpp
std::vector<size_t> sample_L(size_t n, size_t ell, Prng& prng) {
  std::vector<size_t> idx(n);
  std::iota(idx.begin(), idx.end(), 0);
  for (size_t i = 0; i < ell; ++i) {
    size_t j = i + prng.uniform_below(n - i);   // rejection-sampled, NOT modulo
    std::swap(idx[i], idx[j]);
  }
  idx.resize(ell);
  return idx;
}
```

`uniform_below` must use rejection sampling. `rand() % k` is biased and the bias is
concentrated on low indices, which correlates the noise positions.

**Forbidden.** Any per-position Bernoulli draw. Add a lint rule rejecting
`bernoulli_distribution` in `src/encoding/`.

**Acceptance test N1.** `10^6` samples: assert `|L| == ell` on every single draw.
Any failure is a hard stop.

**Acceptance test N2.** Marginal uniformity: each position's inclusion frequency lies
within a 5-sigma interval around `ell/n`. Report the chi-square statistic.

**Acceptance test N3.** Pairwise independence: for 200 random position pairs, the joint
inclusion frequency matches `ell(ell-1)/(n(n-1))` within 5 sigma. This is what catches
a biased `uniform_below`.

**Acceptance test N4.** `L` differs across consecutive batches — see §6.

---

## 6. Seeds, domain separation, concurrency

**Seed hierarchy.**

```
public_seed (32 B, agreed/public)
  |- public_session = KDF(public_seed, "APEQ-v1-public-session" || session_id)
       |- public_pts = KDF(public_session, "APEQ-v1-points") # pts_in, pts_out: PUBLIC

receiver_private_seed (32 B, receiver OS CSPRNG; never sent/logged)
  |- receiver_session = KDF(receiver_private_seed,
                            "APEQ-v1-receiver-session" || session_id)
       |- L_seed = KDF(receiver_session, "APEQ-v1-noise" || batch_ctr)
       |- u_seed = KDF(receiver_session, "APEQ-v1-uvec"  || batch_ctr)
       |- v_seed = KDF(receiver_session, "APEQ-v1-vvec"  || batch_ctr)

sender_private_seed (32 B, sender OS CSPRNG; never sent/logged)
  |- sender_session = KDF(sender_private_seed,
                          "APEQ-v1-sender-session" || session_id)
       |- ab_seed = KDF(sender_session, "APEQ-v1-polyAB" || batch_ctr)
```

KDF is HKDF-SHA256. Every label is a distinct ASCII constant including the version
string; labels are collected in one header so collisions are visible by inspection.

**`batch_ctr` is a strictly increasing 64-bit counter, persisted for the lifetime of
the session.** Reusing `batch_ctr` reuses `L`, and reusing `L` across two batches
reveals the noise positions to anyone who sees both encodings — an immediate total
break. Guard it:

- The counter increments inside `encode()`, before any sampling.
- `encode()` refuses to run twice with the same `(session_id, batch_ctr)`; the object
  keeps a high-water mark and throws on regression.
- The counter is **never** reset by a re-connect. A new connection means a new
  `session_id`.

**Public vs secret.** `pts_in`, `pts_out` and `G` are public and derived from
`public_seed`; both parties derive them independently and must agree. Receiver and
sender private seeds are independent OS-CSPRNG values. They must never share a root:
if the sender learns the seed used for `L`, receiver privacy is destroyed. `L`, `u`,
`A`, `B` and both private seeds must never be serialised, logged, or included in a
debug dump. Mark the members `private` and provide no accessor. **Acceptance test S1:**
capture the log output of a full run and require it to be empty.

**Concurrency.** Each `OleReceiver` / `OleSender` owns its `Prng`. No global RNG state,
no shared mutable state, no thread-local fallback. Parallelism is across sessions only;
within a session the protocol is sequential. **Acceptance test C1:** run 64 sessions
concurrently, assert that all `L` sets are distinct and all outputs correct; run under
ThreadSanitizer.

---

## 7. Correctness tests

**Acceptance test P1 (algebraic identity).** For random `a, b, x` in `F_p^t`, the
reconstructed `y` satisfies `y_i == a_i*x_i + b_i` for all `i`. `10^4` trials, zero
failures.

**Acceptance test P2 (cross-validation).** The C++ backend agrees with
`apeq-ips-ole/reference/apeq_ole.py` on identical seeds and inputs, element by element.
This is the test that catches a wrong evaluation-point ordering.

**Acceptance test P3 (end-to-end APEQ).** With the backend wired into `apeq`, run the
correctness matrix (8/16/32/64 bits × batch 1/10/100/1000/10000), plus an APEQ-only
120- or 126-bit matrix. Add 128-bit only after an injective representation compatible
with the selected field is specified. Expect
**zero false accepts and zero false rejects**, as required by the ideal-OLE
correctness claim. Any failure requires investigation of the implementation,
measurement harness and claimed correspondence to that model.

**Acceptance test P4 (degree hygiene).** Assert `deg(A) <= deg_A`,
`deg(B) <= deg_B`, and `deg(Y) <= ell-1` at runtime under `FP_CHECKED`.
Do not resample a zero leading coefficient: doing so conditions the distribution and
departs from uniform sampling over the required affine spaces. Correctness tests alone
do not establish this distributional property.

---

## 8. Build order

1. **Done:** `Fp` + F1, F2
2. **Done:** polynomial arithmetic (evaluation, interpolation) + Python cross-validation
3. **Done:** `sample_L` + N1–N3
4. **Done except WSL TSAN runtime:** seed hierarchy + S1, N4, C1
5. **Done:** `encode` / `respond` / `reconstruct` against a test-only in-memory
   Retriever + P1, P2, P4
6. **Done:** real semi-honest Retriever using McRosRoy base OT and IKNP chosen-message
   OT extension in `apeq-ips-ole/adapters/libote_retriever.*`
7. **Done:** equality composition in `apeq-docker/docker/bench/apeq_eq.cpp`, with P3 runs
8. **Done:** per-party phase/byte instrumentation and CSV output

Steps 1–5 need no network and no OT library. Step 6 has both local-socket and two-container
TCP tests. Steps 7–8 supply the measured equality driver. Their functional checks
do not establish the concrete-security or software-composition claims discussed
in the root `SECURITY.md`.
