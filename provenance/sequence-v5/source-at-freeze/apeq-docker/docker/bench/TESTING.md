# Testing the shared benchmark harness

`mock_eq.cpp` implements `run_protocol` without a cryptographic dependency. It
tests argument parsing, deterministic inputs, timing fields, correctness and
CSV output before a large third-party image is built.

From `apeq-docker/docker` on Windows PowerShell:

```powershell
docker build --progress=plain -t apeq/mock -f Dockerfile.mock .
.\run_pair.ps1 -Image apeq/mock -Batch 100 -Bits 32 `
  -Results .\mock-results.csv
```

Validate with the Python interpreter configured in PyCharm (replace `python`
with its full path if Python is not on `PATH`):

```powershell
python ..\..\apeq-pipeline\scripts\validate.py .\mock-results.csv
```

The runner deliberately writes one file per party and merges them only after
both containers exit. Never make two containers append to the same bind-mounted
CSV concurrently. `run_all.sh` canonicalizes `RESULTS` and `RUN_DIR` first;
otherwise Docker interprets a relative bind source as a named volume and the host
cannot find the party files.

## What the harness caught while being written

1. Byte counters must mirror between A and B.
2. Timing must vary with batch size instead of using duplicated constants.
3. The APEQ byte lower bound is grouped in full 1024-element encodings rather
   than being linear in the number of active items.

Keep the mock as the first test after any shared harness change. If it fails,
debug the harness before debugging a cryptographic library.

## Real drivers

The shared scaffolding is compiled by the mock. EMP's Yao driver flattens the
whole benchmark batch into one ALICE feed, one BOB feed, one collection of equality
circuits and one batched output reveal. The earlier per-item feed/reveal loop created
an artificial network dependency per comparison: at batch 100 its measured total
slope was approximately 107 RTTs. The batched driver passed 12 executions over
0.5/20/40/80 ms at batch 100 and reduced that slope to approximately 12.0 effective
RTTs (`setup=7.0`, `online=7.0`). A post-metric `NetIO::sync` keeps the generator
alive until the evaluator consumes the final gates; its time and internal one-byte
messages are outside the sampled protocol counters. Batch 1 and 1000 boundary sweeps
also pass, although their effective slopes differ because fresh TCP connections add
payload-dependent congestion-window growth. ABY now exposes separate `yao` and `gmw` variants after applying the pinned
ENCRYPTO_utils `hash_ctr` thread-safety patch; Yao passed 100 two-party acceptance
executions and a direct Yao/GMW smoke also passed. The two variants are separate CSV
cells and must never be averaged. ABY's setup channel is explicitly synchronized
before its phase snapshot, and the asynchronous channel-end marker is made blocking;
otherwise roughly 800 bytes of setup tail traffic are intermittently classified as
online by only one party. Yao and GMW each passed 10 repetitions at both 20 and
40 ms RTT with exact setup/online byte mirroring after this patch. SCI/CrypTFlow2 also builds and
passed 80 two-party LAN executions spanning stability, all supported input
widths, and batches through 1000. Its pinned SEAL dependency receives a GCC 11
compatibility patch, and SCI's three network channels receive explicit receive
counters. VolePSI now builds against its pinned coproto coroutine/socket API and
passed 80 two-party LAN executions: 10 stability repetitions, all supported
input widths, and batches 1/100/1000. Its RsOprf/Paxos keys are domain-separated
by coordinate so repeated narrow values remain valid distinct set keys. The
driver reports coproto sent and received counters and excludes TCP establishment.
An auditable pinned-source patch exposes one preprocessed RsOprf VOLE state: base OT
and silent VOLE are now executed and counted in setup, while `send`/`receive` consume
that state online. A three-run smoke moved Party B from approximately
`setup=0.007 ms / online=39.97 ms` to `setup=41.40 ms / online=1.04 ms` at
batch 100 without materially changing total communication.
The stronger byte-boundary audit subsequently ran 10 repetitions and recovered
the historical lazy-path totals exactly: party B sent 526117 B and received
46717 B on every run (party A was the exact mirror). Only the setup/online
classification changed. Protocol randomness now comes from the OS CSPRNG; the
public CSV seed reproduces inputs only. The holder's final OPRF-output vector now
uses the same post-metric liveness barrier as APEQ-VOLE, preventing a large WAN
batch from closing the socket before the querier consumes the vector while leaving
all reported time and byte counters unchanged.

Use `build_image.sh`, not a bare `docker build`, for measured images. It hashes
the shared source snapshot and injects one `tree-<sha256>` revision into every
driver; `validate.py` rejects successful rows whose provenance is `unknown`.

The baseline input generators accept widths from 1 through 64; the publication
matrix is 8, 16, 24, 32, 48 and 64. The APEQ drivers also support the measured
80/96/120/126-bit inputs. A 128-bit APEQ-OLE row still requires an injective
representation outside the default `p=2^127-1` field. Hashing to the field is not
a zero-error substitute. See the root `SECURITY.md` for the distinction between
correctness testing and a security proof.

The VolePSI driver additionally fixes `field_bits=128`, computational
`kappa=128`, semi-honest security, and statistical security parameter 40.
Unsupported security/field labels are rejected rather than silently producing
a CSV row for a different configuration.

## IPS-OLE backend verification

`apeq/ips-ole-core` and `apeq/ips-ole-libote` are verification images, not
benchmark-driver images, and therefore are intentionally absent from
`run_all.sh`. The core passed one million field cross-checks, one million
fixed-weight samples, 10,000 small-parameter algebraic trials, 100 evaluated-
parameter trials, Python transcript cross-validation, 64 concurrent sessions,
and ASan/UBSan. The
libOTe image uses the VolePSI image's pinned McRosRoy base OT and IKNP extension;
it passed reusable chosen-message OT, full IPS-OLE-over-OT, and a two-container
TCP test with mirrored byte counts. The generic Retriever TCP test deliberately
uses three 512-message calls and reports 128 base OTs and 1536 extended OTs
(`n_ot=1664`) on each side. The protocol tests use the evaluated IPS parameters
`(n,rho,ell,k,t)=(1024,769,255,128,48)` and reject `n/k <= 4`. P4 checks
`deg(A) <= 127` and `deg(B) <= 254`, including valid samples whose leading
coefficients are zero; S1 captures complete test output and requires that no
protocol code emits secret-derived bytes. ThreadSanitizer compiles but cannot start in
this WSL kernel (`unexpected memory mapping`), so C1 under TSAN remains open.

## End-to-end APEQ and Lu et al.

`apeq/apeq` now composes equality as `b_i=-a_i*alpha_i` followed by IPS-OLE
reconstruction; zero is equality. It executes `ceil(batch/48)` complete groups,
uses deterministic dummy padding, counts every padded OT/byte/operation, discards
dummy outputs only before correctness, and reports real base plus extension OTs.
All groups are flattened into one encoding message and one IKNP extension; they
are never executed as sequential network subprotocols.
A real `batch=49` run used two groups and reported 2176 OTs with zero FP/FN.
The holder remains connected through a post-metric liveness barrier while the
querier reconstructs; barrier time and bytes are excluded. This prevents a large
WAN batch from destroying the socket after the holder finishes first. With 209
groups (`batch=10000`), 64-bit inputs and 80 ms RTT, the corrected driver completed
with zero FP/FN and `n_ot=214144`; its online bytes mirrored exactly. The earlier four-point
sweep (before the c8 parameter correction) measured approximately 3.2 online
and 4.1 total effective RTTs; these are historical results. The paper uses the
corrected six-point c8 sweep at 1 Gbit/s: online slopes 4.88--5.04 and total
slopes 5.85--6.02 across the six input widths. These fit per-RTT means of the
larger local duration, not cryptographic round counts.

`apeq/apeq-vole` uses the same pinned libOTe stack as VolePSI. Complete random
silent VOLE is setup; online sends one GF(2^128) correction and one BLAKE2b-128
digest per comparison. Delta is sampled non-zero, so unequal field values differ
and the remaining false-accept event is a 128-bit random-oracle collision. Fifteen
edge runs over 8/24/64-bit inputs and batches 1/48/49/96/100 passed with zero
FP/FN. For each party, online bytes were exactly `16*batch+8`, including framing,
and the audited logical OT count was 880. A low-frequency large-WAN lifecycle race
was later reproduced at batch 10000: the holder could close after flushing while the
querier still consumed the hash vector. A post-metric one-byte liveness barrier now
keeps both endpoints alive; as with the APEQ-OLE barrier, its time and bytes are
sampled out of the protocol metrics.

`apeq/lu` builds the authors' official artifact through a separate patch; the
downloaded source tree stays unchanged. The patch fixes two pinned-libOTe API
compatibility points, exposes base-OT/offline and online phase counters, and
reveals the holder's final XOR share to normalize output to party B. Nine edge
runs over 8/24/64-bit inputs and batches 1/48/100 passed with zero FP/FN. Lu's
base OT and preprocessing are in setup, while its published-style online path
and output reconstruction are in online. Redistribution still requires license
clarification because the upstream archive contains no license file.
