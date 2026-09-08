"""Fixed E3: fresh cryptographic setup per request, cold or shared TCP transport."""
import csv
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
import run_application_v5 as base

JOB = base.PAPER/'experiments/sequence-v5'
BACKENDS = {k:base.BACKENDS[k] for k in ('bit_ot', 'vole_hash')}
utc, write_json, sha, command = base.utc, base.write_json, base.sha, base.command


def prepare():
    if (JOB/'design.json').exists():
        raise RuntimeError('E3 already frozen')
    JOB.mkdir(parents=True, exist_ok=True)
    schedule = [dict(backend=b, mode=m, rep=r, count=20, run_id=str(uuid.uuid4()))
                for b in BACKENDS for m in ('cold', 'warm') for r in range(10)]
    random.Random(0x56354533).shuffle(schedule)
    for rep in range(10):
        directory = JOB/'data'/f'r{rep}'
        for role in ('public', 'private-A', 'private-B', 'truth'):
            (directory/role).mkdir(parents=True)
        ids = [f'p{i:06d}' for i in range(100)]
        (directory/'public/pairs.csv').write_text('pair_id\n'+'\n'.join(ids)+'\n')
        a, b = [base.read_csv(base.JOB/'data'/f'b10000-r{rep:02d}'/f'private-{role}/values.csv') for role in ('A', 'B')]
        for q in range(20):
            aa, bb = a[q*100:(q+1)*100], b[q*100:(q+1)*100]
            for role, records in (('A', aa), ('B', bb)):
                (directory/f'private-{role}/request-{q}.csv').write_text('pair_id,value\n'+''.join(
                    f'{pid},{record["value"]}\n' for pid, record in zip(ids, records)))
            (directory/f'truth/request-{q}.csv').write_text('pair_id,equal\n'+''.join(
                f'{pid},{int(int(ar["value"])==int(br["value"]))}\n' for pid, ar, br in zip(ids, aa, bb)))
    sources = base.source_inputs()
    write_json(JOB/'source-inputs.json', sources)
    # Preserve all driver/header/build files relevant to the new interface.
    for directory in ('apeq-docker/docker/bench', 'apeq-docker/docker/patches'):
        shutil.copytree(base.SOURCE/directory, JOB/'source-at-freeze'/directory)
    for name in ('Dockerfile.apeq-ot', 'Dockerfile.apeq-vole', 'build_image.sh'):
        shutil.copyfile(base.SOURCE/'apeq-docker/docker'/name, JOB/'source-at-freeze/apeq-docker/docker'/name)
    shutil.copyfile(base.SOURCE/'analysis/check_vole_session.cpp', JOB/'source-at-freeze/check_vole_session.cpp')
    write_json(JOB/'schedule.json', schedule)
    write_json(JOB/'data-sha256.json', {p.relative_to(JOB).as_posix():sha(p) for p in sorted((JOB/'data').rglob('*.csv'))})
    design = dict(frozen_utc=utc(), experiment='E3', sequences=40, requests=800, comparisons=80000,
                  requests_per_sequence=20, batch=100, bits=64, network='wan', one_way_ms=40, rate_mbps=100,
                  cpu_set='0-9', repeats=10, cold_connections=400, warm_connections=20,
                  expected_source_revision=base.revision(sources), schedule_seed='0x56354533',
                  strategy='TCP connection reuse only; fresh PRNG/base OT/OT or VOLE material and request namespace each request',
                  inputs='first 2000 frozen E1 fields per rep; 20 disjoint batches of 100; identical across backend/mode',
                  timeout_seconds_per_sequence=180, preflight_sequences=4, preflight_requests_per_sequence=3,
                  primary='sum of 20 B application_ms per independent sequence; excludes process/container launch',
                  inference='10 paired sequence totals per backend; warm minus cold, two-sided 95% t CI df=9',
                  memory='max per-process RSS within sequence; warm values are cumulative high-water marks',
                  excluded='not base-OT caching; not pre-generated correlation batching; not concurrency/software UC',
                  failure='fixed size; retain and stop on failure; no automatic retry')
    write_json(JOB/'design.json', design)
    freeze = {p.relative_to(JOB).as_posix():sha(p) for p in
              (JOB/'design.json', JOB/'schedule.json', JOB/'source-inputs.json', JOB/'data-sha256.json')}
    for p in (Path(__file__), base.PAPER/'tools/run_application_v5.py'):
        freeze['tool:'+p.name] = sha(p)
    freeze['source-test:analysis/check_vole_session.cpp'] = sha(base.SOURCE/'analysis/check_vole_session.cpp')
    write_json(JOB/'freeze.json', freeze)
    print(f'Frozen E3: 40 sequences / 800 requests; {design["expected_source_revision"]}')


def check_freeze():
    for name, expected in json.loads((JOB/'freeze.json').read_text()).items():
        if name.startswith('tool:'):
            path = base.PAPER/'tools'/name[5:]
        elif name.startswith('source-test:'):
            path = base.SOURCE/name[12:]
        else:
            path = JOB/name
        if sha(path) != expected:
            raise RuntimeError('frozen file changed: '+name)
    if base.source_inputs() != json.loads((JOB/'source-inputs.json').read_text()):
        raise RuntimeError('protocol source changed since E3 freeze')
    for name, expected in json.loads((JOB/'data-sha256.json').read_text()).items():
        if sha(JOB/name) != expected:
            raise RuntimeError('E3 data changed: '+name)


def validate_sequence(cell, run, design):
    requests = []
    for q in range(cell['count']):
        truth = base.read_csv(JOB/'data'/f'r{cell["rep"]}'/f'truth/request-{q}.csv')
        observed = base.read_csv(run/'B/results'/f'request-{q}.csv')
        if observed != truth or len(observed) != 100:
            raise RuntimeError('E3 output mismatch')
        parties = []
        for party, role in enumerate(('A', 'B'), 1):
            m = json.loads((run/role/'metrics'/f'request-{q}.json').read_text())
            expected = dict(run_id=cell['run_id']+f'-q{q}', source_revision=design['expected_source_revision'],
                            request_index=q, sequence_requests=cell['count'] if cell['mode']=='warm' else 1,
                            party=party, batch=100, input_bits=64, correct=None, status='completed_unverified',
                            protocol='apeq', backend=BACKENDS[cell['backend']]['backend'],
                            variant=BACKENDS[cell['backend']]['variant'], field_bits=BACKENDS[cell['backend']]['field'],
                            network='wan', rep=cell['rep'], nominal_kappa=128)
            if any(m.get(k)!=value for k, value in expected.items()):
                raise RuntimeError('E3 request metadata mismatch')
            if re.search(r'opened_connections=(\d+)', m['note']).group(1) != '1':
                raise RuntimeError('unexpected transport connection count')
            if 'fresh_crypto_setup_per_request' not in m['note']:
                raise RuntimeError('missing fresh-setup instrumentation')
            for name in ('application_ms', 'input_ms', 'output_ms', 'protocol_call_ms', 'setup_ms', 'online_ms'):
                if not math.isfinite(m[name]) or m[name] < 0:
                    raise RuntimeError('invalid request timing')
            for direction in ('sent', 'recv'):
                if m['bytes_'+direction] != m['setup_bytes_'+direction]+m['online_bytes_'+direction]:
                    raise RuntimeError('request payload sum mismatch')
                if not 0 <= m['bytes_'+direction] < 10**8:
                    raise RuntimeError('possible cumulative-counter underflow')
            parties.append(m)
        requests.append(dict(index=q, correct=True, comparisons=100, parties=parties))
    for role in ('A', 'B'):
        if len(list((run/role/'metrics').glob('request-*.json'))) != cell['count']:
            raise RuntimeError('wrong metrics count')
    result = dict(cell=cell, checked_utc=utc(), correct=True, comparisons=cell['count']*100,
                  connections=1 if cell['mode']=='warm' else cell['count'], requests=requests)
    write_json(run/'validation.json', result)
    return result


def run_sequence(cell, design, images, kind):
    run = JOB/kind/cell['run_id']
    run.mkdir(parents=True)
    data = JOB/'data'/f'r{cell["rep"]}'
    meta = BACKENDS[cell['backend']]
    net = 'apeq-e3-'+cell['run_id'][:8]
    names = [net+'-a', net+'-b']
    command(['docker', 'network', 'create', '--internal', net], timeout=30)
    active = []
    handles = []
    commands = []
    wall_start = time.monotonic()
    write_json(run/'cell.json', dict(cell=cell, started_utc=utc(), loadavg=os.getloadavg()))
    try:
        host = '0.0.0.0'
        party_args = []
        for party, (role, name) in enumerate(zip(('A', 'B'), names), 1):
            (run/role/'metrics').mkdir(parents=True)
            if role=='B':
                (run/role/'results').mkdir()
            command(['docker', 'run', '-d', '--name', name, '--network', net,
                     '--cpuset-cpus', design['cpu_set'], '--cap-add', 'NET_ADMIN',
                     '--mount', f'type=bind,src={data/"public"},dst=/public,readonly',
                     '--mount', f'type=bind,src={data/("private-"+role)},dst=/input,readonly',
                     '--mount', f'type=bind,src={run/role},dst=/out', '--entrypoint', '/bin/sh',
                     images[cell['backend']], '-c', 'exec sleep infinity'], timeout=45)
            command(['docker', 'exec', name, 'tc', 'qdisc', 'replace', 'dev', 'eth0', 'root', 'netem',
                     'limit', 100000, 'delay', '40ms', 'rate', '100mbit'], timeout=20)
            info = json.loads(command(['docker', 'inspect', name], timeout=20))[0]
            mounts = {m['Destination']:m for m in info['Mounts']}
            if set(mounts) != {'/public', '/input', '/out'}:
                raise RuntimeError('unexpected E3 mounts')
            for dest, source, writable in (('/public', data/'public', False),
                    ('/input', data/('private-'+role), False), ('/out', run/role, True)):
                if Path(mounts[dest]['Source']) != source or mounts[dest]['RW'] != writable:
                    raise RuntimeError('wrong E3 mount source/permission')
            write_json(run/(role+'-inspect-start.json'), info)
            args = ['docker', 'exec', name, '/opt/bench/driver', '--protocol', 'apeq',
                    '--backend', meta['backend'], '--variant', meta['variant'], '--batch', 100, '--bits', 64,
                    '--field-bits', meta['field'], '--kappa', 128, '--network', 'wan', '--rtt', 80,
                    '--bandwidth', 100, '--rep', cell['rep'], '--seed', 1, '--run-id', cell['run_id'],
                    '--port', 12345, '--party', party, '--host', host,
                    '--private-input', '/input', '--pair-manifest', '/public/pairs.csv', '--out', '/out/metrics']
            if party==2:
                args += ['--equality-output', '/out/results']
            party_args.append(args)
            if party==1:
                host = info['NetworkSettings']['Networks'][net]['IPAddress']
                if not host:
                    raise RuntimeError('missing E3 holder address')
        deadline = time.monotonic()+design['timeout_seconds_per_sequence']
        count = 1 if cell['mode']=='warm' else cell['count']
        for launch in range(count):
            active = []
            for args, role in zip(party_args, ('A', 'B')):
                request_args = [str(x) for x in args+['--sequence-requests', cell['count'] if cell['mode']=='warm' else 1,
                                                    '--request-index', 0 if cell['mode']=='warm' else launch]]
                commands.append(request_args)
                write_json(run/'driver-commands.json', commands)
                log = (run/f'{role}-launch-{launch}.log').open('w')
                handles.append(log)
                active.append(subprocess.Popen(request_args, stdout=log, stderr=subprocess.STDOUT, text=True))
            exits = [p.wait(timeout=max(0.1, deadline-time.monotonic())) for p in active]
            write_json(run/f'exit-{launch}.json', exits)
            if exits != [0, 0]:
                raise RuntimeError('E3 driver failed: '+str(exits))
        write_json(run/'driver-commands.json', commands)
        write_json(run/'wall-time.json', dict(seconds=time.monotonic()-wall_start, includes_container_and_process_setup=True))
        return validate_sequence(cell, run, design)
    finally:
        for role, name in zip(('A', 'B'), names):
            result = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True, timeout=20)
            (run/(role+'-inspect-end.json')).write_text(result.stdout)
        subprocess.run(['docker', 'rm', '-f', *names], capture_output=True, timeout=30)
        subprocess.run(['docker', 'network', 'rm', net], capture_output=True, timeout=30)
        for p in active:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for h in handles:
            h.close()


def run():
    import fcntl
    lock = (JOB/'job.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (JOB/'status.json').exists():
        raise RuntimeError('E3 already attempted; inspect existing records')
    design = json.loads((JOB/'design.json').read_text())
    status = dict(state='RUNNING', stage='preflight', current='checking frozen E3 artifacts',
                  started_utc=utc(), pid=os.getpid(), completed=0, total=40, preflight_completed=0,
                  current_log='job.stdout.log')
    def update(**kwargs):
        status.update(kwargs, updated_utc=utc())
        write_json(JOB/'status.json', status)
        print(f'{status["updated_utc"]} {status["stage"]} {status["completed"]}/40 {status["current"]}', flush=True)
    try:
        update()
        check_freeze()
        if command(['docker', 'ps', '--format', '{{.Names}}'], timeout=20).strip():
            raise RuntimeError('another Docker workload is active')
        write_json(JOB/'environment.json', dict(utc=utc(), cpu_count=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)),
                   loadavg=os.getloadavg(), meminfo=Path('/proc/meminfo').read_text(),
                   cpuinfo=Path('/proc/cpuinfo').read_text(), docker=command(['docker', 'info'], timeout=30)))
        images = {}
        for backend, meta in BACKENDS.items():
            target = meta['target']
            update(stage='build', current=target, current_log=f'build-{target}.log')
            with (JOB/f'build-{target}.log').open('w') as log:
                subprocess.run(['bash', 'apeq-docker/docker/build_image.sh', target], cwd=base.SOURCE,
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
            info = json.loads(command(['docker', 'image', 'inspect', 'apeq/'+target]))[0]
            images[backend] = info['Id']
            write_json(JOB/f'image-{target}.json', info)
        write_json(JOB/'images.json', images)
        update(stage='domain-test', current='nonce and explicit request-domain checks', current_log='domain-tests.log')
        with (JOB/'domain-tests.log').open('w') as log:
            subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                            '--mount', f'type=bind,src={base.SOURCE/"analysis"},dst=/tests,readonly',
                            '--entrypoint', '/bin/sh', images['vole_hash'], '-c',
                            'cp /tests/check_vole_session.cpp /opt/apeq-vole-bench/apeq_vole_eq.cpp && cmake --build /opt/apeq-vole-bench --parallel 2 && /opt/apeq-vole-bench/driver'],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        for backend in BACKENDS:
            for mode in ('cold', 'warm'):
                cell = dict(backend=backend, mode=mode, rep=0, count=3, run_id=str(uuid.uuid4()))
                update(stage='smoke', current=f'{backend}/{mode}/3 requests', current_log='job.stdout.log')
                run_sequence(cell, design, images, 'smoke')
                update(preflight_completed=status['preflight_completed']+1)
        check_freeze()
        for cell in json.loads((JOB/'schedule.json').read_text()):
            update(stage='E3', current=f'{cell["backend"]}/{cell["mode"]}/rep{cell["rep"]}', current_run_id=cell['run_id'])
            result = run_sequence(cell, design, images, 'runs')
            with (JOB/'completed.jsonl').open('a') as log:
                log.write(json.dumps(dict(run_id=cell['run_id'], correct=result['correct'], checked_utc=utc()))+'\n')
                log.flush()
                os.fsync(log.fileno())
            update(completed=status['completed']+1)
        check_freeze()
        write_json(JOB/'completion.json', dict(completed_utc=utc(), sequences=40, requests=800, comparisons=80000,
                   result_hashes={p.relative_to(JOB).as_posix():sha(p) for p in (JOB/'runs').rglob('*') if p.is_file()}))
        update(state='COMPLETED', stage='complete', current='E3 collected and validated; run independent analysis', current_run_id=None)
    except BaseException as error:
        details = traceback.format_exc()
        if isinstance(error, subprocess.CalledProcessError):
            details += '\n'+str(error.stdout)+'\n'+str(error.stderr)
        (JOB/'error.txt').write_text(details)
        update(state='FAILED', current=str(error), current_log='error.txt')
        raise


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif sys.argv[1:] == ['check-freeze']:
        check_freeze()
    elif sys.argv[1:] == ['run']:
        run()
    else:
        raise SystemExit('usage: run_sequence_v5.py prepare|check-freeze|run')
