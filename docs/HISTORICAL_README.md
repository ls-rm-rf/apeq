# Historical README (superseded)

This is the previous release record. Use the root README and reproduction guide for current commands and security scope. Relative links below refer to the previous repository root.

# APEQ source artifact

This repository contains the source code needed to build and evaluate APEQ and
the comparison baselines used in the paper. It is a source-only release: raw
measurements, normalized CSV files, packet captures, logs, generated tables,
figures, and manuscript build products are intentionally not included.

## Repository layout

- `apeq-ips-ole/`: IPS-OLE core, the libOTe retriever, reference code, and tests.
- `apeq-docker/docker/bench/`: unified drivers for APEQ-OLE, APEQ-VOLE, EMP,
  ABY-Yao, ABY-GMW, SCI/CrypTFlow2, VolePSI, and Lu et al.
- `apeq-docker/docker/`: pinned Docker build recipes, dependency patches, and
  the two-party matrix runner.
- `apeq-pipeline/`: measurement specification, validation, normalization,
  table generation, figure generation, correctness reporting, and effective-
  RTT estimation.
- `analysis/`: candidate-message RS cost analysis, toy decoding diagnostics and
  the stripped plaintext-reply attack experiment. See `analysis/README.md`.
- `experiments/`: publication-matrix launchers and supplementary audit/analysis
  scripts. Their outputs are written outside the source directories and are
  ignored by Git.
- `apeq-lu-eq/`: provenance and acquisition instructions for the official Lu
  et al. artifact.

## Deliberately excluded files

This tree contains no experiment result data. In particular, it excludes all
`*.csv`, `*.log`, `*.pcap`, `party-runs-*`, `.runs-*`, formal-result packages,
generated LaTeX tables, generated PDF figures, container images, build trees,
and caches. The final measurement archive should be published separately from
this source repository.

The synthetic CSV fixtures mentioned by `apeq-pipeline/scripts/README.md` are
also omitted because `gen_synth.py` regenerates them deterministically.

## Prerequisites

- A Linux Docker Engine with permission to create bridge networks and grant
  `NET_ADMIN` to containers.
- Bash, Python 3.10+, `timeout`, `find`, `xargs`, and `sha256sum` on the host.
- For figures: `python3 -m pip install -r apeq-pipeline/requirements.txt`.
- Network access while building the pinned third-party dependencies.

Docker Desktop with a WSL 2 backend is sufficient, but a native Linux host is
the simplest environment for the controlled `tc netem` experiments.

## Build

Run all commands from the repository root unless noted otherwise. If including
Lu in a comparison, acquire its source as described below **before building any
images**. The shared source revision includes its contents when present:

```bash
cd apeq-docker/docker

# Shared dependency stack and the two APEQ variants.
bash ./build_image.sh volepsi
bash ./build_image.sh ips-ole-core
bash ./build_image.sh ips-ole-libote
bash ./build_image.sh apeq
bash ./build_image.sh apeq-vole

# Third-party equality baselines.
bash ./build_image.sh emp
bash ./build_image.sh aby
bash ./build_image.sh cryptflow2
```

Every dependency checkout in the Dockerfiles is pinned. `build_image.sh`
derives a common `tree-<sha256>` identifier from the source snapshot and embeds
it in every result row.

### Lu et al. baseline

The Lu et al. archive contains no license or source-header grant. It is therefore
not redistributed here. Follow `apeq-lu-eq/SOURCE.md`, download the official
artifact, verify its checksum, and extract it as:

```text
apeq-lu-eq/2PC_eq_cmp-main/
```

Then build it with:

```bash
cd apeq-docker/docker
bash ./build_image.sh lu
```

The repository contains only our adapter and auditable patch for that baseline.

## Smoke test

```bash
cd apeq-docker/docker
mkdir -p ../../results
ONLY_PROTOCOLS="apeq" REPS=1 BATCHES="1 48" WIDTHS="32" NETWORKS="lan" \
  RESULTS="../../results/smoke.csv" RUN_DIR="../../results/smoke-runs" \
  bash ./run_all.sh
```

`run_all.sh` launches both parties in isolated containers, applies the selected
network profile, writes one row per party, merges the two files without duplicate
headers, and invokes the validator before returning success.

## Publication matrix

The default values in `run_all.sh` are the common six-width, seven-batch,
LAN/WAN, ten-repetition matrix. To run it explicitly:

```bash
cd apeq-docker/docker
mkdir -p ../../results
REPS=10 \
BATCHES="1 10 48 96 100 1000 10000" \
WIDTHS="8 16 24 32 48 64" \
NETWORKS="lan wan" \
RESULTS="../../results/results-raw.csv" \
RUN_DIR="../../results/party-runs" \
bash ./run_all.sh
```

The scripts in `experiments/` reproduce the additional wide-input, effective-
RTT, E6--E8, and packet-capture checks. Read
`apeq-pipeline/spec/measurement-framework.md` before changing a matrix or phase
boundary.

## Validation and generated outputs

```bash
python3 apeq-pipeline/scripts/validate.py results/results-raw.csv
python3 apeq-pipeline/scripts/make_correctness.py results/results-raw.csv \
  --out-prefix results/correctness
python3 apeq-pipeline/scripts/make_tables.py results/results-raw.csv \
  --outdir results/tables
```

Do not commit these generated files to the source repository.

## Security scope

See [SECURITY.md](SECURITY.md) for the precise proof and implementation scope.
The nominal `security_param=128` does not certify the IPS backend at 128 bits;
the paper's candidate-message analysis reports an interpolation-cost proxy, not
a full attack benchmark. The ideal OLE equality proof does not establish
end-to-end UC security of the measured libOTe composition. The VOLE hash interface
has no session identifier. Full malicious security is not implemented.

See [experiments/REPRODUCING.md](experiments/REPRODUCING.md) for the current
six-point RTT run, verification of the separate c8 archive and reconstruction
of its historical data compositions. New runs receive new source revisions.

## Licensing before publication

No project-wide open-source license has been selected yet. Before making this
repository public, the copyright holder must add the intended license and
complete `RELEASE_CHECKLIST.md`. Third-party projects fetched by the Dockerfiles
remain governed by their own licenses.
