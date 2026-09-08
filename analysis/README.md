# Paper security-analysis sources

For current V5 application scripts and arbitrary mask-degree checks, see
[the reproduction guide](../reproduction/README.md). The old `summarise_tdsc_e2.py`
uses `reproduction/experiments/ole-parameter-sweep/`; that historical E2 parameter
campaign is distinct from V5's E2 application-leakage analysis.

Run from the repository root with Python 3.10 or newer. Only the standard library
is required. The first two commands default to `results/security-analysis/`;
`--outdir PATH` selects another output directory.

```bash
python3 analysis/estimate_rs.py
python3 analysis/check_candidate_attack.py
mkdir -p results/security-analysis
python3 analysis/reproduce_attack_table.py > results/security-analysis/plaintext-attack.md
```

- `estimate_rs.py` reproduces the finite GS monomial/constraint counts, exact
  combinatorial guessing probabilities, interpolation proxy and parameter search
  in the paper's concrete attack-cost assessment and appendix. Outputs:
  `rs-estimates.json`, `rs-examples.csv`, `rs-sensitivity.csv`.
- `check_candidate_attack.py` uses fixed seed 20260907. It runs ten complete
  small-field attacks, ten wrong-candidate toy decodes, twenty root-extractor
  comparisons with exhaustive enumeration, and five conditional algebra checks
  at the measured parameters. Output: `attack-checks.json`. The last five checks
  are explicitly supplied correct guesses; they do not execute a full-size attack.
- `reproduce_attack_table.py` reproduces the four rows of the paper's
  `tab:attack` table, each with twenty deterministic trials. These are attacks on
  the stripped plaintext-reply construction, not on the OT-protected software.
  Its extra elimination-cost bound assumes both R and S evaluations are available.

The 99.3144 interpolation proxy exponent is not certified bit security or a full
attack benchmark. The original attack family, parameters, algebra and random seeds
are preserved here; only output-path handling was adapted for this source release.
See [security scope](../SECURITY.md). Generated outputs are not source files and
should be retained with the separate analysis/result archive.
