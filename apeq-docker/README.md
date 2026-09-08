# Docker benchmark harness

This directory contains the common container build and two-party execution
harness for APEQ and the equality baselines.

## Build context

Run image builds through `docker/build_image.sh`. The script selects the right
Dockerfile, computes one source-tree revision, and uses `docker/` as the build
context. Every benchmark Dockerfile explicitly copies
`bench/driver_common.h`; protocol-specific headers are copied separately.

```bash
cd apeq-docker/docker
bash ./build_image.sh mock
bash ./build_image.sh emp
bash ./build_image.sh aby
bash ./build_image.sh cryptflow2
bash ./build_image.sh volepsi
bash ./build_image.sh ips-ole-core
bash ./build_image.sh ips-ole-libote
bash ./build_image.sh apeq
bash ./build_image.sh apeq-ot
bash ./build_image.sh apeq-vole
```

The Lu et al. source is intentionally absent from this repository because its
official archive provides no redistribution license. After following
`apeq-lu-eq/SOURCE.md` from the repository root and placing the extracted tree
at `apeq-lu-eq/2PC_eq_cmp-main/`, run:

```bash
bash ./build_image.sh lu
```

## Run

`docker/run_all.sh` starts parties A and B on a fresh isolated Docker network,
applies `tc netem`, records separate party rows, and merges them only after both
containers finish. Output paths can be placed anywhere; generated data should
normally go under the ignored repository-level `results/` directory.

```bash
cd apeq-docker/docker
ONLY_PROTOCOLS="apeq" REPS=1 BATCHES="10" WIDTHS="32" NETWORKS="lan" \
  RESULTS="../../results/smoke.csv" RUN_DIR="../../results/smoke-runs" \
  bash ./run_all.sh
```

Important environment variables are `ONLY_PROTOCOLS`, `ONLY_VARIANTS`, `REPS`,
`BATCHES`, `WIDTHS`, `NETWORKS`, `RESULTS`, `RUN_DIR`, `TIMEOUT_S`, and
`APPLY_NETEM`. The common publication widths are 8, 16, 24, 32, 48, and 64.
APEQ-only runs may request 80, 96, 120, or 126 bits. A 128-bit input is rejected
because the prime-field implementation cannot embed it injectively.

The setup/online boundary, byte-counting convention, padding rule, independent
session policy, and result schema are normative in
`apeq-pipeline/spec/measurement-framework.md` from the repository root.
Driver-specific checks are documented in `docker/bench/TESTING.md`.

The V4 targeted campaign also invokes `apeq/apeq-ot` with
`--protocol apeq --backend bit_ot --variant ole --field-bits 127 --kappa 128`.
This classical reference uses one chosen OT per input bit and an additive field
correction. It is intentionally not added to the historical default matrix.
V4 packed OLE transports privately sampled public points during setup; V4 VOLE
exchanges fresh nonces and binds them into every digest. Use the V4 schedule and
separate output record when comparing these interfaces with the frozen matrix.
