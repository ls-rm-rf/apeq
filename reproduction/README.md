# Reproducing V5 application and security results

Run commands from the release root. Preparation and proof diagnostics need
Python 3.10+. Figures and supplementary statistical scripts use root requirements.

## E1: independent private-file requests

First acquire Lu and build the dependency stack in the root README. Use a fresh
release checkout for a new campaign. Preparation refuses to overwrite an existing
frozen design; execution refuses to overwrite an attempted campaign.

```bash
python3 -B reproduction/tools/run_application_v5.py prepare
python3 -B reproduction/tools/run_application_v5.py check-freeze
nohup python3 -B -u reproduction/tools/run_application_v5.py run \
  > reproduction/experiments/application-v5/job.stdout.log \
  2> reproduction/experiments/application-v5/job.stderr.log < /dev/null &
```

The runner builds the four driver images, checks input isolation, runs eight
separate preflights, then executes 240 fixed formal runs (888,000 pair comparisons).
Both network namespaces remain alive until both driver processes finish,
preserving the V5 lifetime fix. No automatic retry or sample extension occurs.
`COMPLETED` requires all expected outputs and hashes to pass.

```bash
python3 -B reproduction/tools/analyse_application_v5.py
```

Outputs: `reproduction/experiments/application-v5/analysis/`, including per-run
data, 24 cell summaries, 18 paired contrasts and the independent audit report.

## E3: cold and warm request sequences

Prepare E3 after E1. Inputs use the first 2,000 fields of each E1 batch-10,000
replication, partitioned into 20 disjoint requests of 100 records.

```bash
python3 -B reproduction/tools/run_sequence_v5.py prepare
python3 -B reproduction/tools/run_sequence_v5.py check-freeze
nohup python3 -B -u reproduction/tools/run_sequence_v5.py run \
  > reproduction/experiments/sequence-v5/job.stdout.log \
  2> reproduction/experiments/sequence-v5/job.stderr.log < /dev/null &
```

Four short preflights precede the 40 sequences / 800 formal requests / 80,000
comparisons. Both modes regenerate base OT, random generators, correlations and
the request namespace. Warm mode also retains process and transport; it does not
isolate transport reuse from process startup effects.

```bash
python3 -B reproduction/tools/analyse_sequence_v5.py
python3 -B reproduction/tools/make_v5_results.py
```

Tables and figure PDFs are written to `reproduction/generated/`. Main results use
request-local B application time. Payload, setup time, process time and memory
have separate definitions. A sequence is the statistical unit for E3.

## Windows launch and monitoring

Prepare from Linux/WSL as above. For a Windows-hosted checkout, PowerShell can
launch the fixed runner in a hidden background WSL process:

```powershell
& './reproduction/tools/start_application_v5.ps1'
& './reproduction/tools/monitor_application_v5.ps1' -Watch
# After E1 analysis and E3 preparation:
& './reproduction/tools/start_sequence_v5.ps1'
& './reproduction/tools/monitor_sequence_v5.ps1' -Watch
```

The launchers use the default WSL distribution; `-Distribution 'NAME'` selects
another installed distribution. Monitors read status every 30 seconds; Ctrl+C
stops only the monitor. Never launch both Linux and Windows background commands
for the same campaign. On failure/interruption, inspect and preserve the attempt
before any rerun.

## Audit the separate historical result archive

`ARCHIVE_ROOT` contains `experiments/application-v5/` and
`experiments/sequence-v5/`, including private synthetic inputs, output files,
designs, schedules, frozen source subsets and completion manifests. These data
are not included in this code-only release.

```bash
python3 -B reproduction/tools/analyse_application_v5.py \
  --archive-root "$ARCHIVE_ROOT" --output-dir results/archived-e1-audit
python3 -B reproduction/tools/analyse_sequence_v5.py \
  --archive-root "$ARCHIVE_ROOT" --output-dir results/archived-e3-audit
```

Archive mode verifies the exact historical harness hashes in `provenance/`.
`--output-dir` keeps the input archive untouched. For a new campaign produced by
this release, omit `--archive-root` to verify current harness hashes. A new
campaign must retain its own source fingerprint.

## E2 and appendix evidence

- `check_bivariate_family_v5.py`: 72 bounded exact-field cases for the arbitrary
  mask-degree affine-target argument.
- `check_bivariate_rank_v4.py`: exact target-rank/recovery checks and reduced-view
  controls. These numerical checks supplement the proof.
- `analysis/check_packed_ole_recovery.cpp`: existing packed all-reply R1 attack.
- `analysis/check_bivariate_repair_attack.py`: earlier affine repair diagnostic.
- `analysis/estimate_rs.py`, `check_candidate_attack.py` and
  `compare_ole_parameters.py`: decoding cost model and toy algebra checks.
- `prepare_r2.py` / `summarise_r2.py` and `prepare_v4.py` / `summarise_v4.py`:
  supplementary fixed schedules and summaries. Preparation requires Linux paths
  and writes a Bash runner into the campaign directory.
- `apeq-docker/docker/run_tdsc_e2.sh` and `analysis/summarise_tdsc_e2.py`: the
  **historical parameter-sensitivity campaign**, not V5 E2's leakage mapping.
  It additionally requires the EMP and packed driver images.

Older matrices, RTT and packet audits remain in `experiments/` and
`apeq-pipeline/`. Frozen subsets are evidence; do not automatically overwrite the
current drivers with them.
