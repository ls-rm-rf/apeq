# Local release validation (2026-09-08)

The packaging changes relocate harness paths, add archive/output selection for
audits, and update documentation. Protocol driver and core implementation bytes
are copied from the existing source tree. The previous source directory was
verified unchanged across all 131 files, including its excluded local files.

Completed checks:

- Source manifest, Python syntax, frozen driver subsets and historical harness
  hashes verified. The source-only inventory excludes raw CSVs, logs, archives,
  compiled products and the separately acquired Lu source. The path/credential
  scan found no matching machine paths or credential signatures in included files.
- All five existing release-tool regressions passed on Linux, including
  independently acquired Lu changes affecting the shared source revision.
- Seven PowerShell scripts parsed; all included Bash scripts passed `bash -n`.
- E1 validator accepted its valid fixture and rejected eight output, provenance,
  duration and byte-counter alterations. E3 accepted its valid fixture and
  rejected five invalid result/sequence/provenance/counter cases.
- The C++ input check was compiled from the release headers in an existing
  isolated container without downloading images. UInt64 boundaries, 15 invalid
  inputs, role-local input isolation and absence of the offline truth vector passed.
- The 72-case affine-family diagnostic passed. Exact rank diagnostics recovered
  all 120 targets and passed all 120 reduced-view controls.
- The release was copied to a different directory containing a space. E1 and E3
  preparation/freeze verification passed there. R2 and V4 schedule generation
  and the generated Bash runner syntax also passed. No formal timed run started.
- The independent E1 audit checked 240 runs, 888,000 comparisons and 3,600 result
  hashes. E3 checked 40 sequences, 800 requests, 80,000 comparisons and 3,980
  result hashes. All seven generated CSV analysis files matched the archived
  analyses. Audit outputs were written outside the source and original data trees.

No new long experiment or full dependency rebuild was performed during packaging.
A clean network-based build of every upstream dependency remains a release check.
This document describes code/integrity validation, not a new performance campaign
or a proof of software security. License selection and public hosting remain pending.
