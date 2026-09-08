#!/usr/bin/env python3
"""Build a deterministic SHA-256 manifest for a formal-results directory."""

import argparse
import csv
import hashlib
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    args = parser.parse_args()
    root = args.package.resolve()
    output = root / "MANIFEST.csv"
    files = sorted(
        (path for path in root.rglob("*") if path.is_file() and path != output),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["relative_path", "bytes", "sha256"])
        for path in files:
            writer.writerow([
                path.relative_to(root).as_posix(),
                path.stat().st_size,
                sha256(path),
            ])
    print(f"wrote {output}: {len(files)} entries")


if __name__ == "__main__":
    main()
