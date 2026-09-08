# APEQ source artifact for the manuscript (V5)

This directory collects the protocol implementations, comparison adapters,
application experiments and analysis code for **APEQ: Security Boundaries and
Setup Costs for Private Record Validation**. The application compares already
aligned private integer fields and returns equality bits only to the querier.
It is a research prototype under static semi-honest assumptions.
[Reproduction guide](reproduction/README.md) ·
[Paper-to-code map](docs/PAPER_TO_CODE.md) · [Security scope](SECURITY.md)

## Contents

| Directory | Purpose |
|---|---|
| `apeq-docker/docker/bench/` | Current bit-OT, packed OLE and session-bound hash-masked VOLE drivers; comparison adapters |
| `apeq-docker/docker/` | Docker recipes with pinned upstream revisions, build script, patches and historical benchmark runner |
| `apeq-ips-ole/` | IPS-OLE core, libOTe adapter and C++ tests |
| `apeq-pipeline/` | Measurement schema, normalization, validation, tables and historical plots |
| `reproduction/tools/` | V5 E1/E3 preparation, execution, monitors, independent audits and figures; selected R2/V4 reproduction tools |
| `analysis/` | Recovery attacks, exact-field diagnostics, decoding-cost analysis and VOLE namespace checks |
| `experiments/` | Earlier main-matrix, RTT and packet-capture tools |
| `provenance/` | Historical E1/E3 design, source hashes, exact frozen driver subsets and harnesses |
| `apeq-lu-eq/` | Acquisition instructions for the separately obtained Lu artifact |

This source package excludes measured results, input CSVs, logs, packet captures,
images, paper sources, compiled binaries and downloaded upstream archives.
Generated results are kept under `results/`, `reproduction/experiments/` or
`reproduction/generated/`, all ignored by Git.

## Local checks without a long experiment

From this directory, with Python 3.10 or newer:

```bash
python3 -B tools/verify_source_release.py
python3 -B -m unittest discover -s experiments/tests -v
python3 -B reproduction/tools/check_application_harness_v5.py
python3 -B reproduction/tools/check_sequence_validator_v5.py
python3 -B reproduction/tools/check_bivariate_family_v5.py
python3 -B reproduction/tools/check_bivariate_rank_v4.py
```

The exact-field checks are proof diagnostics, not security certifications or
performance experiments. Statistical/plot dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Building the comparison stack

Use Linux or a WSL Linux distribution with Docker Engine, Bash and Python 3.
The timed harness requires a quiet Docker host, CPU indices 0–9, and permission
to create private bridge networks and use `NET_ADMIN` for `tc netem`.

Before building the E1 four-backend matrix, acquire the official Lu artifact as
described in [apeq-lu-eq/SOURCE.md](apeq-lu-eq/SOURCE.md). It is not included here.
Acquire it **before** freezing a campaign or building its shared source revision.

```bash
bash apeq-docker/docker/build_image.sh volepsi
bash apeq-docker/docker/build_image.sh ips-ole-core
bash apeq-docker/docker/build_image.sh ips-ole-libote
bash apeq-docker/docker/build_image.sh apeq-ot
bash apeq-docker/docker/build_image.sh apeq-vole
bash apeq-docker/docker/build_image.sh aby
bash apeq-docker/docker/build_image.sh lu
```

The packed historical route additionally uses target `apeq`. Earlier comparisons
also use `emp` and `cryptflow2`. The build script hashes the actual source tree;
new runs retain their new revision instead of claiming historical identifiers.

## Experiments and existing measurement archives

The [reproduction guide](reproduction/README.md) covers E1's 240 fresh executions,
E2's application-leakage reasoning, and E3's 40 sequences of 20 requests each.
Warm E3 retains process and transport while regenerating cryptographic material.
It also explains how to audit existing E1/E3 data without rerunning experiments.

The package cannot regenerate the paper's exact random private fields or
wall-clock measurements without the separate measurement archive. New campaigns
use fresh operating-system randomness and preserve the experimental design.
Historical fingerprints and frozen subsets are documented in
[provenance/README.md](provenance/README.md).

## Security and release status

The ideal OLE guarantees do not establish end-to-end software UC security.
The current VOLE driver includes session nonces and an explicit request namespace
for sequences. The historical packed configuration is not certified at 128-bit
security. See [SECURITY.md](SECURITY.md).

Source repository: <https://github.com/anonymous/apeq-artifact>.
This is a locally prepared release package. The authors have not yet selected a project-wide license;
third-party code remains subject to its own terms. See
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) and [THIRD_PARTY.md](THIRD_PARTY.md).
