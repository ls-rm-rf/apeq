"""Check the source manifest, provenance, syntax and accidental private artifacts."""
from pathlib import Path
import ast
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SKIP_ROOTS = ('results/', 'reproduction/experiments/', 'reproduction/generated/', 'release-checks/')
SKIP_PARTS = {'.git', '__pycache__', '.venv', '.pytest_cache'}
FORBIDDEN_SUFFIXES = {'.csv', '.tsv', '.log', '.pcap', '.pcapng', '.zip', '.tar', '.gz',
                      '.exe', '.dll', '.so', '.a', '.o', '.obj', '.pdf', '.pptx', '.pyc'}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def source_files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
                  and not SKIP_PARTS.intersection(p.relative_to(ROOT).parts)
                  and not p.relative_to(ROOT).as_posix().startswith(SKIP_ROOTS)
                  and p.name != 'SOURCE_MANIFEST.json')


def main():
    files = source_files()
    expected = json.loads((ROOT/'SOURCE_MANIFEST.json').read_text())['files']
    actual = {p.relative_to(ROOT).as_posix(): sha(p) for p in files}
    assert actual == expected, 'Source files differ from the release manifest'
    python_count = 0
    local_path = re.compile(r'(?:[A-Za-z]:[\\/](?:Users|pycharm)[\\/]|/mnt/[a-z]/pycharm/|/home/[A-Za-z0-9_.-]+/|\b\d{8}comparision\b)')
    secret = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}')
    for p in files:
        rel = p.relative_to(ROOT).as_posix()
        assert p.suffix.lower() not in FORBIDDEN_SUFFIXES, rel
        assert '2PC_eq_cmp-main' not in p.relative_to(ROOT).parts, rel
        assert p.name not in ('.env', 'credentials.json'), rel
        text = p.read_text(encoding='utf-8-sig')
        assert not local_path.search(text), 'Machine-specific path: '+rel
        assert not secret.search(text), 'Potential secret: '+rel
        if p.suffix == '.py':
            ast.parse(text, filename=rel)
            python_count += 1
    for campaign in ('application-v5', 'sequence-v5'):
        base = ROOT/'provenance'/campaign
        freeze = json.loads((base/'freeze.json').read_text())
        for key in ('design.json', 'source-inputs.json'):
            assert sha(base/key) == freeze[key]
        for key, value in freeze.items():
            if key.startswith('tool:'):
                assert sha(base/'tools'/key[5:]) == value
        inputs = json.loads((base/'source-inputs.json').read_text())
        for p in (base/'source-at-freeze').rglob('*'):
            if not p.is_file():
                continue
            rel = p.relative_to(base/'source-at-freeze').as_posix()
            value = freeze['source-test:analysis/check_vole_session.cpp'] if rel == 'check_vole_session.cpp' else inputs[rel]
            assert sha(p) == value, rel
    print(json.dumps(dict(source_files=len(files), python_sources=python_count,
                          manifest_verified=True, frozen_subsets_verified=True,
                          generated_results_and_upstream_lu_excluded=True,
                          project_license_present=(ROOT/'LICENSE').is_file()), indent=2))


if __name__ == '__main__':
    main()
