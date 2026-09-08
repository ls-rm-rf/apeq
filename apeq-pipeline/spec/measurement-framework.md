# APEQ Measurement Framework — Specification

**Status: schema v2 frozen (2026-08-29).** Phase byte counters, Lu et al. and the
RTT sweep were added before the formal matrix. Any later schema change requires a
full re-run. Read this before writing measurement code.

---

## 0. Why this document exists

The previous version of this work reported per-comparison communication of 8.4 bytes
(67 bits) at batch size 10 000, and identical timing rows for batch sizes 10 and 100.
Both are impossible: the protocol cannot transmit fewer bytes than its message
structure requires, and two different batch sizes cannot cost exactly the same.

Both artefacts had the same root cause: measurement by external sampling tools
(`iftop`, `time`) rather than by in-protocol instrumentation, and hand-transcribed
tables. This specification exists to make those failure modes structurally impossible.

Three rules follow, and everything below is an elaboration of them:

1. **Bytes are counted inside the protocol**, at the socket wrapper, never by an
   external sniffer. An external tool is used only as a cross-check.
2. **Every measured run emits one CSV row.** Tables and figures are generated from the
   CSV by script. No number is ever typed into LaTeX by hand.
3. **Every run records the seed and full parameter set**, so any row can be reproduced
   in isolation.

---

## 1. CSV schema

One row per `(protocol, params, repetition)`. Written append-only to `results.csv`
with this exact header. Fields must appear in this order.

```
run_id,timestamp_utc,git_commit,hostname,
protocol,backend,variant,
batch_size,input_bits,field_bits,security_param,
network,rtt_ms,bandwidth_mbps,
rep,seed,
party,
setup_ms,online_ms,total_ms,
setup_bytes_sent,setup_bytes_recv,
online_bytes_sent,online_bytes_recv,
bytes_sent,bytes_recv,
peak_rss_kb,
n_ot,n_field_ops,
correct,n_false_pos,n_false_neg,
status,note
```

### Field definitions

| Field | Type | Notes |
|---|---|---|
| `run_id` | string | UUIDv4, identical for both parties of the same execution. This is what joins A's row to B's row. |
| `timestamp_utc` | ISO 8601 | Start of the run. |
| `git_commit` | string | Git short hash. A release archive without `.git` uses `tree-<12 hex chars>`, the shared source-tree SHA-256 emitted by `build_image.sh`. `unknown` is rejected. A dirty Git tree writes `<hash>-dirty` and is excluded from published tables. |
| `hostname` | string | Distinguishes the two machines in the two-host setup. |
| `protocol` | enum | `apeq`, `emp_eq`, `aby_eq`, `cryptflow2_eq`, `volepsi_eq`, `lu_eq` |
| `backend` | enum | `ips_ole`, `ferret_vole`, `n/a` |
| `variant` | enum | `ole`, `vole_hash`, `yao`, `gmw`, `n/a`. ABY-Yao and ABY-GMW are separate rows; they must never be averaged. |
| `batch_size` | int | Number of equality tests in this execution. |
| `input_bits` | int | Current drivers accept 1–64; the publication matrix uses 8, 16, 24, 32, 48, 64. Wider inputs require a new shared representation. |
| `field_bits` | int | `log2(p)` rounded up, or the extension degree for binary fields. |
| `security_param` | int | 80 or 128. Required nominal configuration label; it does not certify concrete security of the IPS backend. See the root `SECURITY.md`. |
| `network` | enum | `lan`, `wan`, `round_sweep`. The last label is reserved for the constant-bandwidth RTT experiment. |
| `rtt_ms`, `bandwidth_mbps` | float | The *configured* `tc` values, not measured ones. Measured RTT goes in `note`. |
| `rep` | int | 0-indexed repetition. |
| `seed` | uint64 | Reproduces the public workload and input pair. Cryptographic protocol coins are sampled independently from the OS CSPRNG and are never logged or derived from this public value. |
| `party` | enum | `A` (holder) or `B` (querier). **Each execution writes two rows.** |
| `setup_ms` | float | See §2. |
| `online_ms` | float | See §2. |
| `total_ms` | float | `setup_ms + online_ms`. Stored redundantly as a consistency check. |
| `setup_bytes_sent`, `setup_bytes_recv` | uint64 | Application payload attributed to setup/offline. |
| `online_bytes_sent`, `online_bytes_recv` | uint64 | Application payload attributed to online execution and output normalization. |
| `bytes_sent`, `bytes_recv` | uint64 | Application-layer payload, from the socket wrapper. See §3. |
| `peak_rss_kb` | uint64 | From `getrusage(RUSAGE_SELF).ru_maxrss`. |
| `n_ot` | uint64 | Base + extended OTs consumed. APEQ must report the Retriever's real counter. `0` means inapplicable or unavailable for a third-party baseline, not “the protocol used no OT”. |
| `n_field_ops` | uint64 | Multiplications only; `-1` if not instrumented for this protocol. |
| `correct` | bool | Whether all `batch_size` outputs matched the plaintext reference. |
| `n_false_pos`, `n_false_neg` | int | Written by party B; A writes `-1`. |
| `status` | enum | `ok`, `timeout`, `oom`, `crash`, `skipped` |
| `note` | string | Free text, **comma-free**. Measured RTT, exception messages, etc. |

### Invariants checked by the analysis script

The loader rejects the dataset if any of these fail. This is not optional — it is what
catches the class of error described in §0.

- Every `run_id` appears exactly twice, once with `party=A` and once with `party=B`.
- `A.bytes_sent == B.bytes_recv` and `B.bytes_sent == A.bytes_recv`, within the framing
  overhead recorded by the wrapper.
- Setup and online byte counters mirror independently, and each total counter equals
  its setup plus online counters exactly.
- `bytes_sent + bytes_recv >= batch_size * theoretical_min_bytes(protocol, params)`,
  where `theoretical_min_bytes` is computed independently from the protocol description.
  **This is the check that would have caught the 67-bit figure.**
- `total_ms == setup_ms + online_ms` within 1 ms.
- No two rows share `(protocol, backend, variant, batch_size, input_bits, field_bits,
  network, rtt_ms, bandwidth_mbps, rep, party)`.
- For any fixed configuration, `bytes_sent` is non-decreasing in `batch_size`.
  Communication is bounded below by a linear function of the batch; a decrease indicates
  a counter reset bug.

---

## 2. Timing convention

Both parties time themselves. Never use the shell's `time`, and never time only one
side.

```
setup_ms   : from process start of protocol work to the end of all input-independent
             precomputation. For APEQ this covers base OTs, OT extension setup, and
             noisy-encoding generator setup. Includes any network round trips that do
             not depend on the inputs.
online_ms  : from the first input-dependent operation to the moment the party's output
             is available. For B this ends when out[] is fully populated.
```

Use `std::chrono::steady_clock`. Take the timestamp *inside* the party object, not in
`main()`, so that process startup and argument parsing are excluded.

If one party finishes its transcript before the output party completes expensive
local reconstruction, it must remain connected through a post-metric liveness
barrier. Snapshot time and byte counters before that barrier; the barrier is an
orchestration guard, not a protocol message, and must not enter any reported metric.

Establish the TCP/channel transport before starting `setup_ms`, then reset byte
counters and start both parties' setup timers at that boundary. A blocking server
constructor otherwise measures the host launcher's delay before it starts the client
container, inflating only party A. TCP connection establishment, container startup and
argument parsing are orchestration costs, not cryptographic setup; base OTs and every
subsequent input-independent network round trip remain inside `setup_ms`.

Rationale for the split: at `batch_size = 1` the baselines are dominated by base-OT
setup, which is amortised away at larger batches. Reporting only `total_ms` would
flatter APEQ at small batches and mislead at large ones. **Both columns must appear in
the paper**; the headline table reports `online_ms` with `setup_ms` in an adjacent
column, and the caption states the convention explicitly.

Every repetition is an independent complete session. A fresh pair of containers runs
base OT and every reusable setup once for that repetition; no setup state is reused
between repetitions or matrix cells. Thus base OT is counted once in every successful
execution row. This conservative rule is uniform across protocols and avoids a special
first-row convention.

---

## 3. Byte counting

All traffic passes through a single wrapper. There is no other socket in the codebase.

```cpp
class CountingChannel {
public:
    void send(const void* buf, size_t n) {
        bytes_sent_ += n;          // payload only
        inner_->send(buf, n);
    }
    void recv(void* buf, size_t n) {
        bytes_recv_ += n;
        inner_->recv(buf, n);
    }
    uint64_t bytes_sent() const { return bytes_sent_; }
    uint64_t bytes_recv() const { return bytes_recv_; }
private:
    uint64_t bytes_sent_ = 0, bytes_recv_ = 0;
    Channel* inner_;
};
```

Rules:

- Count **application payload**, not TCP/IP headers. State this in the paper caption.
  Baselines must be counted the same way — if a baseline library reports its own
  counters, verify they use the same convention before mixing them.
- For baselines that cannot be instrumented internally, capture with
  `tcpdump -w` on a dedicated port and subtract header bytes. Record the method in
  `note`.
- **Cross-check**: for at least one configuration per protocol, compare the in-protocol
  counter against `tcpdump`. If they disagree by more than the expected framing
  overhead, there is a bug. Record the outcome in the artifact, not just in the paper.
- Record setup and online deltas at the same channel. For VolePSI, the explicit
  preprocessing patch must preserve the old lazy path's total bytes exactly; moving
  the boundary is not allowed to add or remove traffic.
- ABY's background receive thread can account a message on the opposite side of its
  local setup/online snapshot. Raw endpoint rows are always retained. Publication
  analysis runs `normalize_aby_phases.py`, which uses the phase recorded by each
  direction's sender as authoritative and copies only that direction's receive phase
  counters to the peer row. It never changes timing, sender bytes, or another protocol.

---

## 4. Experiment matrix

```
protocol      : apeq(ole), apeq(vole_hash), emp_eq, aby_eq(yao), aby_eq(gmw), cryptflow2_eq, volepsi_eq, lu_eq
batch_size    : 1, 10, 48, 96, 100, 1000, 10000
input_bits    : 8, 16, 24, 32, 48, 64
network       : lan, wan
rep           : 0..9
```

Full matrix: 8 variants × 7 batches × 6 widths × 2 networks × 10 repetitions
= 6720 executions = 13440 CSV rows. Run WAN first; LAN may be reduced to key
configurations only if the experiment budget is constrained, but such a reduction must
be stated before analysis rather than selected after seeing results. The APEQ-only
wide-input harness now supports the measured 80/96/120/126-bit inputs. The default prime field
cannot injectively represent every 127- or 128-bit input, and hashing into it is
forbidden because that would replace perfect correctness with collision probability.

APEQ encodes `t=48` comparisons per IPS-OLE group. For a requested batch `b`, the
driver must execute `ceil(b/48)` complete groups, pad the final group with deterministic
dummy inputs, count all padded-group time/communication/OTs, and discard dummy outputs
  before correctness accounting. In particular, `n_ot` includes the OTs for all 1024
codeword positions in every padded group. All groups in one execution are combined
into one encoding message and one batched IKNP extension; groups must not be run as
sequential network subprotocols, because that would make measured rounds grow with
`ceil(b/48)` and invalidate the constant-round claim.

- **Timeout**: 300 s per execution. On timeout write `status=timeout`, leave timing
  fields empty, and **do not** substitute a value. The analysis script reports timeouts
  as a separate annotation on the figure; it never averages over them or drops them
  silently. (The earlier version's WAN figure had a discontinuity caused by exactly
  this.)
- **Repetitions**: 10 per cell. The paper reports mean and sample standard deviation.
  Any cell whose relative standard deviation exceeds 20% is flagged in the analysis
  output for investigation before publication.
- **Correctness**: every execution verifies its output against a plaintext reference
  and writes `correct`, `n_false_pos`, `n_false_neg`. A cell containing any
  `correct=false` row is excluded from timing tables and reported separately. For
  `apeq(ole)` the expected value is zero false accepts across the entire matrix — this
  follows from the ideal-OLE correctness claim. The experiment is a functional
  check of the implementation, not a cryptographic security proof.
- **Correctness report**: `make_correctness.py` emits a separate protocol × width ×
  batch table with executions, comparisons, false positives and false negatives.

### Network emulation

LAN and WAN are produced with `tc netem` on the loopback or the inter-host link:

```
LAN : rtt 0.5 ms,  bandwidth 1 Gbps
WAN : rtt 80 ms,   bandwidth 100 Mbps
```

The harness sets `netem limit 100000` and configures no random loss. Its default
1000-packet queue is smaller than some deliberately batched messages and otherwise
creates accidental drops and TCP retransmission timeouts; this experiment varies only
RTT and bottleneck rate, not loss or queue pressure.

The current RTT experiment uses RTT 0.5, 10, 20, 40, 60 and 80 ms at 1 Gbps,
with ten independent sessions per setting. These rows use `network=round_sweep`;
the main WAN matrix instead uses 100 Mbps. For each execution,
`estimate_rounds.py` takes the larger local phase duration max(A,B), then fits
the six per-RTT means. R² describes those six means, not the 60 individual
executions. Unsynchronized phase starts mean this metric is not the interval
from the earliest start to the latest finish. The slope measures transport
sensitivity, not the abstract cryptographic message-round count: fresh TCP
connections are used, so
large one-directional messages can add RTT-dependent slow-start or flow-control cost.
Keep batch size and payload fixed when comparing slopes, report the tested batch, and
use small- and large-batch boundary sweeps to expose transport dependence. A paper may
call the slope an “effective RTT count”, but must not relabel it as the protocol's
theoretical round count without separately ruling out these transport effects.

Record the configured values in the CSV, and the measured RTT (from `ping`) in `note`.
The paper must state whether the two parties ran on one host or two. If one host, say
so and note that it inflates nothing but also removes NIC effects.

---

## 5. From CSV to LaTeX

```
scripts/
  docker/run_all.sh # drives executions, writes results.csv, resumable
  validate.py       # enforces every invariant in §1; exits non-zero on failure
  make_tables.py    # results.csv -> tables/*.tex
  make_figures.py   # results.csv -> figures/*.pdf
  make_correctness.py # results.csv -> P3 correctness CSV/Markdown
  estimate_rounds.py  # RTT sweep -> effective-round CSV/Markdown
```

- `make_tables.py` writes complete `tabular` environments. **No number is typed into
  the manuscript by hand.** This is what prevents duplicated rows.
- `make_figures.py` uses **logarithmic y-axes** and logarithmic x-axes for batch-size
  sweeps. Linear axes compress everything except the slowest protocol into an
  indistinguishable band near zero.
- Figures are: (a) time vs `input_bits` at fixed batch; (b) time vs `batch_size` at
  fixed width; (c) the same two for communication. **Do not average across batch sizes**
  — such an average is dominated entirely by the largest batch and carries no
  information.
- Legends take protocol names from the CSV enum, so they cannot drift out of sync with
  the citation numbering.
- Every figure caption states: network setting, `security_param`, number of
  repetitions, and whether error bars are standard deviation.

---

## 6. Pre-publication checklist

- [ ] `validate.py` exits zero on the final `results.csv`.
- [ ] Every table and figure in the manuscript was produced by script from that file.
- [ ] `git_commit` is identical and clean across all published rows, or every row has the same `tree-<sha256>` archive revision.
- [ ] The `tcpdump` cross-check is recorded for at least one configuration per protocol.
- [ ] Record the nominal `security_param = 128` configuration and state the
      backend-specific limitations in `SECURITY.md`; do not call this matched
      certified 128-bit security.
- [ ] Timeout and correctness-failure cells are annotated, not silently omitted.
- [ ] The paper states the byte-counting convention and the setup/online split.
- [ ] Every repetition used an independent complete session; no setup state was reused.
- [ ] P3 correctness and effective-RTT reports were generated from the final CSV.
