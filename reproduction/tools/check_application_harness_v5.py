"""Verify that the offline auditor rejects altered output and provenance."""
import importlib.util
import json
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location('v5', Path(__file__).with_name('run_application_v5.py'))
v5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v5)

with tempfile.TemporaryDirectory() as directory:
    v5.JOB = Path(directory)
    v5.write_workload(v5.JOB/'data/test', [0, 2**64-1, 42], [0, 1, 42])
    run = v5.JOB/'run'
    (run/'A').mkdir(parents=True)
    (run/'B').mkdir()
    result = run/'B/equality.csv'
    correct_output = 'pair_id,equal\np000000,1\np000001,0\np000002,1\n'
    result.write_text(correct_output)
    cell = dict(backend='bit_ot', workload='test', batch=3, run_id='fixture', network='lan', rep=0)
    design = dict(expected_source_revision='test-revision')
    base = dict(run_id='fixture', source_revision='test-revision', batch=3, input_bits=64,
                field_bits=127, protocol='apeq', backend='bit_ot', variant='ole', network='lan',
                rep=0, correct=None, status='completed_unverified', nominal_kappa=128,
                input_ms=1, protocol_call_ms=2, output_ms=1, application_ms=4.1,
                setup_ms=1, online_ms=1, setup_bytes_sent=10, setup_bytes_recv=10,
                online_bytes_sent=5, online_bytes_recv=5, bytes_sent=15, bytes_recv=15, peak_rss_kb=10)
    for party, role in enumerate(('A', 'B'), 1):
        v5.write_json(run/role/'metrics.json', dict(base, party=party, equal_count=2 if party==2 else None))
    assert v5.validate_pair(cell, run, design)['correct']
    rejected = 0
    for bad in ('pair_id,equal\np000000,1\np000001,1\np000002,0\n',
                'pair_id,equal\np000002,1\np000001,0\np000000,1\n',
                'pair_id,equal\np000000,1\np000001,0\n'):
        result.write_text(bad)
        try:
            v5.validate_pair(cell, run, design)
        except RuntimeError:
            rejected += 1
        else:
            raise AssertionError('accepted incorrect output')
    result.write_text(correct_output)
    b = json.loads((run/'B/metrics.json').read_text())
    for change in (dict(source_revision='different'), dict(correct=True), dict(application_ms=-1),
                   dict(bytes_sent=16), dict(equal_count=1)):
        v5.write_json(run/'B/metrics.json', dict(b, **change))
        try:
            v5.validate_pair(cell, run, design)
        except RuntimeError:
            rejected += 1
        else:
            raise AssertionError('accepted invalid metrics')
    assert rejected == 8
print('PASS: correct fixture; 8 altered-output/provenance/timing/byte cases rejected')
