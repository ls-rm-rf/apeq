# Experiment launchers

These scripts are the source code used for the formal and supplementary
measurement campaigns. They resolve the repository root from their own path;
no machine-specific drive or user directory is required.

- `run_round_sweep.sh`: complete current six-RTT run, validation and plotting.
- `compose_replacement_results.py` and `compose_round_results.py`: reconstruct
  the corrected c8 main and RTT compositions from archived overlays.
- `run_formal_lan_background.sh`: common LAN matrix.
- `run_formal_round_widths_background.sh`: six-width effective-RTT scan.
- `run_formal_apeq_wide_background.sh`: APEQ-only 120/126-bit matrix.
- `run_formal_e6_e8_background.sh`: E6 batch crossover, E7 intermediate wide
  inputs, and E8 additional RTT profiles.
- `run_e6_e8_preflight.sh`: one-cell preflight for E6--E8.
- `run_tcpdump_audit.sh` and `analyze_tcpdump_audit.py`: packet-level payload
  cross-check.
- `analyze_vole_setup_decomposition.py`: base-OT/silent-VOLE setup analysis.
- `analyze_e6_crossover.py`: APEQ-OLE/APEQ-VOLE communication crossover.
- `compose_formal_results.py` and `merge_result_csvs.py`: deterministic result
  composition utilities.
- `build_manifest.py` and `verify_formal_package.py`: separate result-archive
  packaging checks.

The historical campaign suffixes in output filenames are retained so that the
scripts map unambiguously to the paper's archived data. All outputs are ignored
by the source repository's `.gitignore`.

Use [REPRODUCING.md](REPRODUCING.md) for current commands, c8 data mapping and
explicit archive paths. Other campaign launchers retain their historical scope.

Run the release-tool regression checks from the repository root:

```bash
python3 -B -m unittest discover -s experiments/tests -v
```

Linux runs additionally check
that edits to independently acquired Lu source change the shared build revision;
these tests use a fake Docker command and do not build images.
