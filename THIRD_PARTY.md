# Third-party source policy

The Dockerfiles fetch pinned revisions of EMP-toolkit, ABY, EzPC/SCI,
VolePSI, libOTe, cryptoTools, and their transitive dependencies during image
construction. Those projects are not vendored in this repository and remain
subject to their upstream licenses.

The files under `apeq-docker/docker/patches/` record the minimal changes used by
the experiments. The unified drivers under `apeq-docker/docker/bench/` are part
of this project.

The official Lu et al. equality artifact is handled differently because its
downloaded archive contains no license notice. Its source and archive are not
redistributed. See `apeq-lu-eq/SOURCE.md` for the official DOI and checksum.
