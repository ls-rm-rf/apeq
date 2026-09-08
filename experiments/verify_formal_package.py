#!/usr/bin/env python3
"""Verify package hashes and all canonical publication datasets."""

import argparse
import csv
import hashlib
import subprocess
import sys
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_manifest(root):
    manifest = root / "SHA256SUMS.txt"
    failures = []
    if manifest.is_file():
        rows = []
        for line in manifest.read_text(encoding="utf-8-sig").splitlines():
            digest, relative = line.split(maxsplit=1)
            rows.append({"relative_path": relative.removeprefix("*"), "sha256": digest})
    else:
        manifest = root / "MANIFEST.csv"
        if not manifest.is_file():
            print(f"missing manifest in {root}: expected SHA256SUMS.txt or MANIFEST.csv",
                  file=sys.stderr)
            return False
        with manifest.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
    for row in rows:
        path = (root / row["relative_path"]).resolve()
        if not path.is_relative_to(root) or path == manifest:
            failures.append(f"invalid manifest path: {row['relative_path']}")
            continue
        if not path.is_file():
            failures.append(f"missing: {row['relative_path']}")
            continue
        actual_size = path.stat().st_size
        actual_hash = sha256(path)
        if "bytes" in row and actual_size != int(row["bytes"]):
            failures.append(f"size mismatch: {row['relative_path']}")
        if actual_hash != row["sha256"]:
            failures.append(f"hash mismatch: {row['relative_path']}")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest
    }
    listed = {row["relative_path"] for row in rows}
    if len(listed) != len(rows):
        failures.append("duplicate manifest paths")
    for extra in sorted(actual - listed):
        failures.append(f"unlisted: {extra}")
    if failures:
        for failure in failures:
            print(f"MANIFEST ERROR: {failure}", file=sys.stderr)
        return False
    print(f"manifest: {len(rows)} files verified")
    return True


def validate(root, relative, commits=()):
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "apeq-pipeline/scripts/validate.py"),
        str(root / relative),
    ]
    for commit in commits:
        command.extend(["--allow-commit", commit])
    print(f"validating {relative}")
    return subprocess.call(command) == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path, help="separately acquired result archive")
    parser.add_argument("--manifest-only", action="store_true",
                        help="check file integrity only, without applying current c8 data rules")
    args = parser.parse_args()
    root = args.package.resolve()
    if not verify_manifest(root):
        return 1
    if args.manifest_only:
        print("MANIFEST VERIFIED (data semantics not checked)")
        return 0
    ok = True
    revision = "tree-05290e9816c7"
    jobs = [
        ("data/formal-main-c8-composed.csv",
         ("tree-76a322079fc9", "tree-8251da8a3300", "tree-b1174342219d", revision)),
        ("data/formal-round-widths-c8-composed.csv",
         ("tree-8251da8a3300", "tree-b1174342219d", revision)),
        ("data/apeq-ole-c8-wide.csv", (revision,)),
    ]
    for (relative, _), expected_rows in zip(jobs, (17400, 5760, 80)):
        if not (root / relative).is_file():
            print(f"missing publication input: {relative}", file=sys.stderr)
            return 1
        with (root / relative).open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != expected_rows or any(
            row["protocol"] == "apeq" and row["variant"] == "ole"
            and row["git_commit"] != revision for row in rows
        ):
            print(f"C8 coverage/provenance mismatch: {relative}", file=sys.stderr)
            ok = False
    for relative, commits in jobs:
        ok = validate(root, relative, commits) and ok
    if ok:
        print("PACKAGE VERIFIED")
        return 0
    print("PACKAGE VERIFICATION FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
