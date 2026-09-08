# Frozen source provenance

E1 used `tree-2606d821ba4e`; E3 used `tree-cd12d6cd44b1`. They are separate
builds and datasets. Each campaign directory contains the original design,
freeze manifest, complete source-input hash list, saved driver/build subset and
exact harness files named in the freeze. Private CSVs, schedules, host details,
metrics, logs and completion records belong to the separate data archive.

`source-at-freeze/` is a **subset**, not a standalone historical checkout. The
full source-input list includes independently acquired Lu files. Check those
hashes against the separate artifact when reconstructing a historical build.
Do not overlay snapshots on current drivers automatically or reuse an archived
identifier for a fresh build.

`assembly-inputs.json` maps copied files to source categories and hashes before
portability edits. The release-root `SOURCE_MANIFEST.json` records final files.
The exact historical harness copies retain their original workflow messages for
hash verification. Execute `reproduction/tools/`, not these frozen copies.
