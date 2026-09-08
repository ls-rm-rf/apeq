"""Regression checks for archive integrity and downloaded-source provenance.

Run: python3 -B -m unittest discover -s experiments/tests -v
The Bash checks use a fake Docker executable; no image is built.
"""

import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "package_verifier", ROOT / "experiments/verify_formal_package.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class ArchiveIntegrity(unittest.TestCase):
    def test_csv_manifest_checks_size_and_missing_manifest_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(verifier.verify_manifest(root))
                (root / "sample.txt").write_bytes(b"original")
                digest = hashlib.sha256(b"original").hexdigest()
                manifest = root / "MANIFEST.csv"
                header = "relative_path,bytes,sha256\n"
                manifest.write_text(header + f"sample.txt,8,{digest}\n")
                self.assertTrue(verifier.verify_manifest(root))
                manifest.write_text(header + f"sample.txt,9,{digest}\n")
                self.assertFalse(verifier.verify_manifest(root))

    def test_hashes_detect_tampering_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            data = root / "sample.txt"
            data.write_bytes(b"original")
            digest = hashlib.sha256(data.read_bytes()).hexdigest()
            (root / "SHA256SUMS.txt").write_text(f"{digest}  sample.txt\n")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertTrue(verifier.verify_manifest(root))
                data.write_bytes(b"modified")
                self.assertFalse(verifier.verify_manifest(root))
                data.write_bytes(b"original")
                (root / "unlisted.txt").write_bytes(b"extra")
                self.assertFalse(verifier.verify_manifest(root))

    def test_manifest_cannot_read_outside_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / "package"
            root.mkdir()
            (root.parent / "outside.txt").write_bytes(b"outside")
            digest = hashlib.sha256(b"outside").hexdigest()
            (root / "SHA256SUMS.txt").write_text(f"{digest}  ../outside.txt\n")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertFalse(verifier.verify_manifest(root))


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "requires Linux/Bash")
class LinuxReleaseEntrypoints(unittest.TestCase):
    def test_round_sweep_requires_normalized_validation_and_complete_fits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "experiments").mkdir()
            (root / "apeq-docker/docker").mkdir(parents=True)
            launcher = root / "experiments/run_round_sweep.sh"
            shutil.copyfile(ROOT / "experiments/run_round_sweep.sh", launcher)
            (root / "apeq-docker/docker/run_all.sh").write_text(
                '#!/bin/bash\n'
                '[[ "$NETWORKS" == "rtt0p5 rtt10 rtt20 rtt40 rtt60 rtt80" ]] || exit 90\n'
                '[[ "$REPS" == 10 && "$BATCHES" == 100 ]] || exit 91\n'
                'echo configured > "$RUN_DIR/../configuration-ok"\n'
                'exit 1\n')
            # No data or Docker execution: simulate phase-attribution rejection,
            # followed by success or failure of the required downstream checks.
            binaries = root / "bin"
            binaries.mkdir()
            python = binaries / "python3"
            python.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == *"$FAIL_STAGE"* ]]; then exit 7; fi\n'
                'exit 0\n')
            python.chmod(0o755)
            (root / "results/round-sweep/party-runs").mkdir(parents=True)
            for stage, expected in (("never-match", 0),
                                    ("normalize_aby_phases", 7),
                                    ("estimate_rounds", 7),
                                    ("make_round_width_figure", 7)):
                env = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"],
                           FAIL_STAGE=stage)
                result = subprocess.run(["bash", str(launcher)], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                self.assertTrue((root / "results/round-sweep/configuration-ok").is_file())

    def test_lu_edits_change_shared_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(
                "results", "artifacts", "__pycache__", "2PC_eq_cmp-main"))
            binaries = root / "bin"
            binaries.mkdir()
            docker = binaries / "docker"
            docker.write_text("#!/bin/sh\nexit 0\n")
            docker.chmod(0o755)
            env = dict(os.environ, PATH=str(binaries) + os.pathsep + os.environ["PATH"])
            script = source / "apeq-docker/docker/build_image.sh"

            def revision():
                result = subprocess.run(["bash", str(script), "mock"], env=env,
                                        check=True, capture_output=True, text=True)
                return re.search(r"revision=(tree-[0-9a-f]+)", result.stdout)[1]

            without_lu = revision()
            upstream = source / "apeq-lu-eq/2PC_eq_cmp-main"
            upstream.mkdir()
            sample = upstream / "main.cpp"
            sample.write_text("// downloaded source version one\n")
            first = revision()
            self.assertNotEqual(without_lu, first)
            self.assertEqual(first, revision())
            sample.write_text("// downloaded source version two\n")
            self.assertNotEqual(first, revision())


if __name__ == "__main__":
    unittest.main()
