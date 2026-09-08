"""Bounded validator regression: reject wrong results, provenance and sequence ordinals."""
import json
from pathlib import Path
import tempfile
import run_sequence_v5 as e3

with tempfile.TemporaryDirectory() as directory:
    e3.JOB = Path(directory)
    data, run = e3.JOB/'data/r0/truth', e3.JOB/'fixture'
    data.mkdir(parents=True)
    for role in ('A', 'B'):
        (run/role/'metrics').mkdir(parents=True)
    (run/'B/results').mkdir()
    output = 'pair_id,equal\n'+''.join(f'p{i:06d},{i%2}\n' for i in range(100))
    (data/'request-0.csv').write_text(output)
    (run/'B/results/request-0.csv').write_text(output)
    cell = dict(backend='bit_ot', mode='cold', count=1, run_id='test', rep=0)
    for party, role in enumerate(('A', 'B'), 1):
        metric = dict(run_id='test-q0', source_revision='fixture', request_index=0, sequence_requests=1,
                      party=party, batch=100, input_bits=64, correct=None, status='completed_unverified',
                      protocol='apeq', backend='bit_ot', variant='ole', field_bits=127,
                      network='wan', rep=0, nominal_kappa=128, note='fresh_crypto_setup_per_request opened_connections=1')
        for name in ('application_ms', 'input_ms', 'output_ms', 'protocol_call_ms', 'setup_ms', 'online_ms'):
            metric[name] = 1.0
        for direction in ('sent', 'recv'):
            metric['bytes_'+direction] = 10
            metric['setup_bytes_'+direction] = 8
            metric['online_bytes_'+direction] = 2
        e3.write_json(run/role/'metrics/request-0.json', metric)
    design = dict(expected_source_revision='fixture')
    assert e3.validate_sequence(cell, run, design)['correct']
    path = run/'B/metrics/request-0.json'
    good = json.loads(path.read_text())
    for change in (dict(request_index=1), dict(source_revision='wrong'),
                   dict(note='fresh_crypto_setup_per_request opened_connections=2'), dict(bytes_sent=2**64-1)):
        e3.write_json(path, dict(good, **change))
        try:
            e3.validate_sequence(cell, run, design)
        except RuntimeError:
            pass
        else:
            raise AssertionError('invalid sequence metrics accepted')
    e3.write_json(path, good)
    (run/'B/results/request-0.csv').write_text(output.replace('p000000,0', 'p000000,1'))
    try:
        e3.validate_sequence(cell, run, design)
    except RuntimeError:
        pass
    else:
        raise AssertionError('incorrect sequence output accepted')
print('PASS: valid fixture plus 5 invalid result/sequence/provenance/counter cases')
