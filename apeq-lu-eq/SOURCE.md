# Lu et al. constant-round equality artifact

Source paper: Tianpei Lu et al., *Efficient 2PC for Constant Round Secure
Equality Testing and Comparison*, USENIX Security 2025 / IACR ePrint 2024/949.

Official artifact record:
<https://doi.org/10.5281/zenodo.17217396>

Expected download:

```text
2PC_eq_cmp-main.zip
MD5 3b60198360efde3be77160941c4833d6
```

## Acquisition

The upstream archive and extracted source are intentionally not bundled in this
repository. Download the file from the official artifact record, verify its MD5
checksum, and extract it so that the repository contains:

```text
apeq-lu-eq/2PC_eq_cmp-main/CMakeLists.txt
apeq-lu-eq/2PC_eq_cmp-main/main.cpp
...
```

Acquire this source before building any image in a comparison matrix. The build
script includes the extracted files in the shared content revision when present;
changing them requires rebuilding all images used together.

`apeq-docker/docker/build_image.sh lu` then supplies this directory as a
read-only BuildKit context. `Dockerfile.lu` copies it into the image and applies
`patches/lu-eq-phase-accounting.patch` there; the downloaded directory itself is
not modified.

## Integration decision

The benchmark uses the authors' artifact rather than a reimplementation. Our
separate adapter provides deterministic per-party inputs, preserves the
artifact's offline/online split, counts both communication directions, and maps
the output to the common CSV schema.

## Licensing note

No `LICENSE` file or source-header license notice was present in the downloaded
archive used for the experiments. Clarify reuse and redistribution terms with
the authors or artifact record before publishing their source. Keeping only the
provenance record, adapter, and patch in this repository is the conservative
release path.
