# Reproducing the current paper

Run commands from the source repository root. This source package excludes raw
results. Obtain the separate measurement archives before checking historical
results. No verified public archive URL or DOI has been assigned in this package.

## New measurements from this source

Follow the root README to acquire Lu's source and build the images. Acquire Lu
before building **any** image in a comparison matrix: its source contents are
included in the shared revision when present. Changing those contents or any
other hashed source changes the revision; rebuild all images for a matched run.

```bash
python3 -m pip install -r apeq-pipeline/requirements.txt
bash experiments/run_round_sweep.sh
```

This entry runs eight protocol variants, six input widths, batch 100, ten fresh
sessions, and RTTs 0.5/10/20/40/60/80 ms at 1 Gbit/s. It normalizes ABY byte-phase
attribution, validates results, computes the 48 fits and draws the RTT figure.
Outputs go to `results/round-sweep/`. Each fit uses six means of the larger local
phase duration, with ten sessions per mean; R² is computed on those six means.
The figure uses ReportLab's portable Times fonts, so font metrics may differ
slightly from the original Windows figure while plotted data remain the same.

The root README's main matrix is a broader Cartesian run. The historical paper's
corrected OLE main slice uses all listed batches at 64 bits and all six widths at
batch 100. New measurements get a new content revision and must not be relabelled
`tree-05290e9816c7` or substituted for historical runs without explanation.

## Validate the paper's archived c8 measurements

Set `C8` to the extracted `formal-results-c8-20260905` archive:

```bash
C8=/path/to/formal-results-c8-20260905
python3 experiments/verify_formal_package.py "$C8"
```

The checker verifies the archive's `SHA256SUMS.txt` (or a `MANIFEST.csv` produced
by `build_manifest.py`), then uses the validator shipped in this source repository.
It checks these publication inputs and keeps their historical source revisions:

| Input | Rows | Accepted revisions |
| --- | ---: | --- |
| `data/formal-main-c8-composed.csv` | 17,400 | 76a322079fc9, 8251da8a3300, b1174342219d, 05290e9816c7 |
| `data/formal-round-widths-c8-composed.csv` | 5,760 | 8251da8a3300, b1174342219d, 05290e9816c7 |
| `data/apeq-ole-c8-wide.csv` | 80 | 05290e9816c7 |

All revisions have the `tree-` prefix. OLE rows in these inputs must specifically
use `tree-05290e9816c7`. Earlier interrupted CSVs in the archive are audit traces;
they are not substituted for these inputs. The unchanged VOLE wide-input rows
come from the earlier archive and retain their original provenance.

The old archive can be checked for file integrity explicitly. This does not apply
the current c8 structural bounds to its obsolete OLE rows and does not validate
their measurement semantics:

```bash
python3 experiments/verify_formal_package.py /path/to/formal-results-final-20260830 \
  --manifest-only
```

To regenerate the current RTT fit and figure without new measurements:

```bash
mkdir -p results/paper-reproduction
python3 apeq-pipeline/scripts/estimate_rounds.py \
  "$C8/data/formal-round-widths-c8-composed.csv" \
  --allow-commit tree-8251da8a3300 --allow-commit tree-b1174342219d \
  --allow-commit tree-05290e9816c7 --out-prefix results/paper-reproduction/rounds
python3 apeq-pipeline/scripts/make_round_width_figure.py \
  results/paper-reproduction/rounds.csv results/paper-reproduction/rounds.pdf
```

## Reconstruct the c8 compositions

Set `OLD` to the earlier `formal-results-final-20260830` archive. The following
utilities preserve baseline rows and replace OLE rows using the saved overlays.
Run the archive checker first; composition is not a substitute for validation.

```bash
OLD=/path/to/formal-results-final-20260830
mkdir -p results/paper-reproduction
python3 experiments/compose_replacement_results.py \
  "$OLD/data/formal-main-extended-normalized-final.csv" \
  "$C8/data/apeq-ole-c8-revised.csv" results/paper-reproduction/main.csv \
  --networks lan wan \
  --cell 8:100 --cell 16:100 --cell 24:100 --cell 32:100 --cell 48:100 \
  --cell 64:1 --cell 64:10 --cell 64:48 --cell 64:96 --cell 64:100 \
  --cell 64:200 --cell 64:400 --cell 64:800 --cell 64:1000 --cell 64:10000
python3 experiments/compose_round_results.py \
  "$OLD/data/formal-round-widths-6rtt-normalized-final.csv" \
  "$C8/data/apeq-ole-c8-round-width.csv" results/paper-reproduction/round-input.csv
```

The scripts with historical campaign suffixes remain available for provenance.
In particular, the old RTT launcher runs four RTTs and the E8 launcher supplies
the other two. Use `run_round_sweep.sh` for a new complete six-point run.

Security-analysis reproduction is documented in [analysis/README.md](../analysis/README.md).
