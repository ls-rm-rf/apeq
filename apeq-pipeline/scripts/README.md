# APEQ measurement pipeline

Implements the workflow of `spec/measurement-framework.md`. No number in the
manuscript is ever typed by hand.

```
run_matrix.py    -> results.csv          (drives executions; to be written with the C++ impl)
validate.py      -> exit 0/1             (enforces every invariant; run first)
make_tables.py   -> tables/*.tex
make_figures.py  -> figures/*.pdf
```

`make_tables.py` and `make_figures.py` both invoke `validate.py` and refuse to
run if it fails. Pass `--skip-validate` only for debugging, never for a build
that will be submitted.

`make_tables.py` derives the available network profiles and RTT labels from the
CSV. It emits online, setup, total, communication, and amortised tables only for
profiles actually present, so a WAN-only dataset cannot silently produce empty
LAN tables.

## What validate.py catches

Each check corresponds to a defect found in the previous version of this work:

| Check | Defect it prevents |
|---|---|
| structural communication lower bound | a reported 8.4 B (67 bit) per comparison at batch 10 000 |
| byte-identical timing across batch sizes | batch-10 and batch-100 rows duplicated by copy-paste |
| A/B byte-counter mirroring | one-sided or externally sampled measurement |
| monotone communication in batch size | counter reset mid-run |
| `total_ms == setup_ms + online_ms` | inconsistent timing convention |
| mandatory `security_param` | missing nominal configuration labels; this check does not certify concrete backend security |
| timeout rows carry no substituted timing | discontinuities from averaging over dropped runs |
| perfect correctness for `apeq/ole` | an observed mismatch with the ideal-model correctness claim |
| single clean `git_commit` | tables assembled from mixed builds |

## Testing the pipeline itself

`gen_synth.py` builds a clean dataset and five deliberately defective ones. All
five must fail validation:

```
python3 gen_synth.py
python3 validate.py synth_clean.csv        # PASSED
python3 validate.py synth_bad_comm.csv     # FAILED
python3 validate.py synth_dup_rows.csv     # FAILED
python3 validate.py synth_mismatch.csv     # FAILED
python3 validate.py synth_falsepos.csv     # FAILED
python3 validate.py synth_nonmono.csv      # FAILED
```

Keep this as a regression test. If a change to `validate.py` lets any of the
five pass, the change is wrong.

## Dependencies

`validate.py` and `make_tables.py`: standard library only.
`make_figures.py`: matplotlib.
`make_round_width_figure.py`: reportlab; uses the built-in Times fonts and needs
no operating-system font paths. From the repository root:

```bash
python3 -m pip install -r apeq-pipeline/requirements.txt
```

The RTT estimator fits per-RTT means of the larger local phase duration; R²
refers to these mean points. See `experiments/REPRODUCING.md` from the repository
root for the six-point run and the separately archived c8 paper data.
