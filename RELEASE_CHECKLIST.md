# Public-release checklist

V5 local packaging is complete. Current validation is recorded in
[docs/VALIDATION.md](docs/VALIDATION.md). The remaining unchecked publication
items below are not claims that experiments still need to be collected.

- [x] Collect current protocol code, E1/E3 harnesses, validators and statistical scripts.
- [x] Preserve historical E1/E3 fingerprints and exact frozen source subsets.
- [x] Remove machine-specific workspace dependencies from active entry points.
- [x] Exclude upstream Lu source/archive and measured data from the release package.
- [x] Run the source inventory, short regressions, native input check and archive audits.
- [x] Test preparation and generated launchers from a relocated directory containing spaces.

- [ ] Assign a permanent repository or archival DOI, verify that it is public,
  and add the verified location to the manuscript and source README.
- [ ] Select and add a project-wide open-source `LICENSE` for the authors' code.
- [ ] Confirm that every contributor agrees to that license.
- [ ] Keep the unlicensed Lu et al. source archive out of this repository unless
  the authors or artifact record provide explicit redistribution permission.
- [x] Run the source-only audit and confirm that no CSV, logs, packet captures,
  build products, credentials, or local absolute paths are tracked.
- [ ] Build each Docker image from a fresh clone and run the smoke test in
  `README.md`.
- [ ] Publish the raw measurement archive separately, with its own manifest and
  checksums, if the venue requires result-data availability.

- [ ] Review `SECURITY.md` and keep nominal parameters distinct from certified
  security; do not promote functional tests to UC or malicious-security proofs.
- [ ] Reproduce `analysis/README.md` outputs and archive them separately.
- [ ] Verify the separate c8 package with `experiments/verify_formal_package.py`.
- [ ] Acquire Lu before building the shared comparison stack; preserve the actual
  source revision in every new run and the original revisions in historical data.
