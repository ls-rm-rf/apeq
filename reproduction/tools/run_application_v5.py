"""Fixed E1 job. Preparation is portable; execution uses a Linux Docker daemon.

No automatic retries, no adaptive sample count, no analysis or manuscript edits.
The parent blocks on subprocess completion, rather than polling Docker progress.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import uuid

PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parent
SOURCE = ROOT
JOB = PAPER/'experiments/application-v5'
BACKENDS = {
    'bit_ot': dict(target='apeq-ot', protocol='apeq', backend='bit_ot', variant='ole', field=127),
    'vole_hash': dict(target='apeq-vole', protocol='apeq', backend='ferret_vole', variant='vole_hash', field=128),
    'lu': dict(target='lu', protocol='lu_eq', backend='n/a', variant='n/a', field=128),
    'aby_yao': dict(target='aby', protocol='aby_eq', backend='n/a', variant='yao', field=128),
}


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    os.replace(temp, path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def source_inputs():
    """Match build_image.sh's byte-level source revision (paths sorted as bytes)."""
    paths = set()
    for directory in ('apeq-docker/docker/bench', 'apeq-docker/docker/patches',
                      'apeq-pipeline/spec', 'apeq-ips-ole', 'apeq-lu-eq/2PC_eq_cmp-main'):
        paths.update(p for p in (SOURCE/directory).rglob('*') if p.is_file())
    paths.update((SOURCE/'apeq-pipeline/scripts').glob('*.py'))
    paths.update(p for p in (SOURCE/'apeq-lu-eq').glob('*') if p.is_file())
    paths.update((SOURCE/'apeq-docker/docker').glob('Dockerfile.*'))
    paths.update(SOURCE/'apeq-docker/docker'/p for p in
                 ('build_image.sh', 'run_all.sh', 'run_pair.ps1', 'write_status_rows.py'))
    return {p.relative_to(SOURCE).as_posix(): sha(p)
            for p in sorted(paths, key=lambda p: p.relative_to(SOURCE).as_posix().encode())}


def revision(inputs):
    lines = ''.join(f'{v}  {k}\n' for k, v in inputs.items())
    return 'tree-'+hashlib.sha256(lines.encode()).hexdigest()[:12]


def private_decimal(value, i, party):
    # An explicit integer-field normalization workload, not name matching.
    return (' \t'+str(value)+' ' if (i+party) % 10 == 0 else
            '000'+str(value) if (i+party) % 10 == 1 else str(value))


def write_workload(directory, alpha, beta):
    for role in ('public', 'private-A', 'private-B', 'truth'):
        (directory/role).mkdir(parents=True)
    files = {
        'public/pairs.csv': ['pair_id'],
        'private-A/values.csv': ['pair_id,value'],
        'private-B/values.csv': ['pair_id,value'],
        'truth/equality.csv': ['pair_id,equal'],
    }
    for i, (a, b) in enumerate(zip(alpha, beta)):
        pid = f'p{i:06d}'
        files['public/pairs.csv'].append(pid)
        files['private-A/values.csv'].append(f'{pid},{private_decimal(a, i, 1)}')
        files['private-B/values.csv'].append(f'{pid},{private_decimal(b, i, 2)}')
        files['truth/equality.csv'].append(f'{pid},{int(a == b)}')
    for name, lines in files.items():
        (directory/name).write_text('\n'.join(lines)+'\n', encoding='utf-8')


def prepare():
    if (JOB/'design.json').exists():
        raise RuntimeError('frozen design already exists; refusing to overwrite')
    JOB.mkdir(parents=True, exist_ok=True)
    schedule = [dict(backend=backend, batch=batch, network=network, rep=rep)
                for backend in BACKENDS for batch in (100, 1000, 10000)
                for network in ('lan', 'wan') for rep in range(10)]
    random.Random(0x56354531).shuffle(schedule)
    for i, cell in enumerate(schedule):
        cell['run_id'] = str(uuid.uuid4())
        cell['index'] = i+1
        cell['workload'] = f'b{cell["batch"]}-r{cell["rep"]:02d}'
    # Private values are generated once using OS entropy, not a public seed.
    # Frozen files, not a secret-generating seed, are the reproduction artifact.
    for rep in range(10):
        a = [secrets.randbits(64) for _ in range(10000)]
        b = [x if secrets.randbelow(2) else x ^ (1 << secrets.randbelow(64)) for x in a]
        # Repeated private values at distinct authorized pairs are legal.
        for i in range(20, len(a), 20):
            a[i], b[i] = a[i-1], b[i-1]
        for batch in (100, 1000, 10000):
            write_workload(JOB/'data'/f'b{batch}-r{rep:02d}', a[:batch], b[:batch])
    # Correctness-only edge inputs do not enter the timing matrix.
    a = [0, 2**64-1, 2**63, 2**32, 7, 7, 1, 10]
    b = [0, 2**64-1, 2**63-1, 2**32+1, 7, 8, 0, 10]
    write_workload(JOB/'data/edge', a, b)
    inputs = source_inputs()
    for name in ('apeq-docker/docker/bench/driver_common.h',
                 'apeq-docker/docker/bench/apeq_ot_eq.cpp',
                 'apeq-docker/docker/bench/apeq_vole_eq.cpp',
                 'apeq-docker/docker/bench/apeq_vole_digest.h',
                 'apeq-docker/docker/bench/aby_eq.cpp',
                 'apeq-docker/docker/bench/lu_eq.cpp',
                 'apeq-docker/docker/build_image.sh'):
        dest = JOB/'source-at-freeze'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE/name, dest)
    for target in BACKENDS.values():
        name = 'apeq-docker/docker/Dockerfile.'+target['target']
        shutil.copyfile(SOURCE/name, JOB/'source-at-freeze'/name)
    write_json(JOB/'source-inputs.json', inputs)
    write_json(JOB/'schedule.json', schedule)
    write_json(JOB/'data-sha256.json', {p.relative_to(JOB).as_posix(): sha(p)
                                       for p in sorted((JOB/'data').rglob('*.csv'))})
    design = dict(frozen_utc=utc(), experiment='E1', runs=240, repeats=10,
                  batch_sizes=[100, 1000, 10000], input_bits=64,
                  backends=BACKENDS, expected_source_revision=revision(inputs),
                  networks={'lan': {'one_way_ms': 0.25, 'rate_mbps': 1000},
                            'wan': {'one_way_ms': 40, 'rate_mbps': 100}},
                  schedule_seed='0x56354531', cpu_set='0-9', timeout_per_pair_seconds=600,
                  dataset='controlled synthetic aligned uint64 integer identifiers',
                  values='OS entropy; no input-generating seed in public configuration',
                  sharing='same frozen values across all backends and networks at each batch/rep',
                  primary_latency='B local input read through result file close; process startup excluded',
                  other_latency='A local latency includes waiting for B; protocol phases reported separately',
                  io='warm host cache possible; output close included, fsync not performed',
                  payload='raw per-library counters; no wire-byte claim; asymmetric snapshots preserved',
                  statistics='10 independent sessions/cell; mean and sample SD; no stable p95 claim',
                  primary_contrasts='paired by rep: VOLE minus bit-OT, Lu minus bit-OT, ABY minus bit-OT, per batch/network; two-sided 95% t CI df=9; 18 descriptive CIs, no multiplicity-adjusted discovery claim',
                  E3='separate sequence campaign with fresh cryptographic setup per request',
                  failure='stop and retain; no automatic retries or exclusions')
    write_json(JOB/'design.json', design)
    freeze = {p.relative_to(JOB).as_posix(): sha(p) for p in
              (JOB/'design.json', JOB/'schedule.json', JOB/'data-sha256.json', JOB/'source-inputs.json')}
    freeze.update({'tool:'+p.name: sha(p) for p in (Path(__file__), PAPER/'tools/check_application_io_v5.cpp')})
    write_json(JOB/'freeze.json', freeze)
    print(json.dumps(dict(prepared=True, runs=240, source=revision(inputs), directory=str(JOB))))


def check_freeze():
    for name, digest in json.loads((JOB/'freeze.json').read_text()).items():
        path = PAPER/'tools'/name[5:] if name.startswith('tool:') else JOB/name
        if sha(path) != digest:
            raise RuntimeError('frozen artifact changed: '+name)
    expected = json.loads((JOB/'source-inputs.json').read_text())
    if source_inputs() != expected:
        raise RuntimeError('source changed since freeze; refusing mixed-source collection')
    for name, digest in json.loads((JOB/'data-sha256.json').read_text()).items():
        if sha(JOB/name) != digest:
            raise RuntimeError('frozen dataset changed: '+name)


def command(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs).stdout


def validate_pair(cell, run, design):
    truth = read_csv(JOB/'data'/cell['workload']/'truth/equality.csv')
    observed = read_csv(run/'B/equality.csv')
    if len(observed) != cell['batch'] or len(truth) != cell['batch']:
        raise RuntimeError('output count mismatch')
    fp = fn = 0
    for expected, got in zip(truth, observed):
        if expected['pair_id'] != got['pair_id'] or got['equal'] not in ('0', '1'):
            raise RuntimeError('output identity or bit mismatch')
        fp += expected['equal']=='0' and got['equal']=='1'
        fn += expected['equal']=='1' and got['equal']=='0'
    if (run/'A/equality.csv').exists():
        raise RuntimeError('unauthorized holder output')
    parties = [json.loads((run/role/'metrics.json').read_text()) for role in ('A', 'B')]
    backend = BACKENDS[cell['backend']]
    for party, metrics in enumerate(parties, 1):
        expected = dict(run_id=cell['run_id'], source_revision=design['expected_source_revision'],
                        party=party, batch=cell['batch'], input_bits=64, field_bits=backend['field'],
                        protocol=backend['protocol'], backend=backend['backend'], variant=backend['variant'],
                        network=cell['network'], rep=cell['rep'], correct=None,
                        status='completed_unverified', nominal_kappa=128)
        if any(metrics.get(k)!=v for k, v in expected.items()):
            raise RuntimeError('application metadata mismatch')
        for name in ('input_ms', 'protocol_call_ms', 'output_ms', 'application_ms', 'setup_ms', 'online_ms'):
            if not math.isfinite(metrics[name]) or metrics[name]<0:
                raise RuntimeError('invalid timing')
        if metrics['input_ms']+metrics['protocol_call_ms']+metrics['output_ms'] > metrics['application_ms']+0.01:
            raise RuntimeError('application timing components exceed total')
        for direction in ('sent', 'recv'):
            if metrics['setup_bytes_'+direction]+metrics['online_bytes_'+direction] != metrics['bytes_'+direction]:
                raise RuntimeError('phase payload sum mismatch')
        if metrics['peak_rss_kb'] <= 0:
            raise RuntimeError('missing RSS measurement')
    if parties[0]['equal_count'] is not None or parties[1]['equal_count'] != sum(int(r['equal']) for r in observed):
        raise RuntimeError('output summary mismatch')
    result = dict(cell=cell, checked_utc=utc(), correct=fp==fn==0, false_pos=fp, false_neg=fn,
                  comparisons=cell['batch'], verifier='offline host; truth never mounted into parties',
                  raw_party_metrics=parties,
                  payload_A_sent_minus_B_recv=parties[0]['bytes_sent']-parties[1]['bytes_recv'],
                  payload_B_sent_minus_A_recv=parties[1]['bytes_sent']-parties[0]['bytes_recv'])
    write_json(run/'validation.json', result)
    if fp or fn:
        raise RuntimeError(f'correctness failure fp={fp}, fn={fn}')
    return result


def run_pair(cell, design, images, kind):
    run = JOB/kind/cell['run_id']
    run.mkdir(parents=True)  # No reuse of partial or completed runs.
    workload = JOB/'data'/cell['workload']
    meta = BACKENDS[cell['backend']]
    net = 'apeq-v5-'+cell['run_id'][:8]
    names = [net+'-a', net+'-b']
    profile = design['networks'][cell['network']]
    common = ['--protocol', meta['protocol'], '--backend', meta['backend'], '--variant', meta['variant'],
              '--field-bits', meta['field'], '--batch', cell['batch'], '--bits', 64, '--kappa', 128,
              '--network', cell['network'], '--rtt', 2*profile['one_way_ms'],
              '--bandwidth', profile['rate_mbps'], '--rep', cell['rep'], '--seed', 1,
              '--run-id', cell['run_id'], '--port', 12345,
              '--private-input', '/input/values.csv', '--pair-manifest', '/public/pairs.csv',
              '--out', '/out/metrics.json']
    # Keep the network namespace alive after either driver exits. Otherwise
    # deleting B's container can discard a final reply still in its netem queue
    # while A awaits that reply. The idle PID 1 is outside application timing.
    wrapper = 'exec sleep infinity'
    write_json(run/'cell.json', dict(cell=cell, started_utc=utc(), loadavg=os.getloadavg()))
    command(['docker', 'network', 'create', '--internal', net], timeout=30)
    drivers = []
    log_handles = []
    driver_commands = []
    try:
        host = '0.0.0.0'
        for party, name in enumerate(names, 1):
            role = 'A' if party==1 else 'B'
            (run/role).mkdir()
            args = ['docker', 'run', '-d', '--name', name, '--network', net,
                    '--cpuset-cpus', design['cpu_set'], '--cap-add', 'NET_ADMIN',
                    '--mount', f'type=bind,src={workload/"public"},dst=/public,readonly',
                    '--mount', f'type=bind,src={workload/("private-"+role)},dst=/input,readonly',
                    '--mount', f'type=bind,src={run/role},dst=/out',
                    '--entrypoint', '/bin/sh', images[cell['backend']], '-c', wrapper]
            driver_args = ['docker', 'exec', name, '/opt/bench/driver', *common,
                           '--party', party, '--host', host]
            if party==2:
                driver_args += ['--equality-output', '/out/equality.csv']
            command(args, timeout=45)
            # Complete shaping before launching either timed driver.
            command(['docker', 'exec', name, 'tc', 'qdisc', 'replace', 'dev', 'eth0',
                     'root', 'netem', 'limit', 100000, 'delay', f'{profile["one_way_ms"]}ms',
                     'rate', f'{profile["rate_mbps"]}mbit'], timeout=20)
            driver_commands.append([str(x) for x in driver_args])
            info = json.loads(command(['docker', 'inspect', name], timeout=15))[0]
            mounts = {m['Destination']: m for m in info['Mounts']}
            if set(mounts) != {'/public', '/input', '/out'} or mounts['/input']['RW'] or mounts['/public']['RW']:
                raise RuntimeError('unexpected input/output mounts')
            for dest, source in (('/public', workload/'public'), ('/input', workload/('private-'+role)), ('/out', run/role)):
                if Path(mounts[dest]['Source']) != source:
                    raise RuntimeError('wrong party mount')
            write_json(run/(role+'-inspect-start.json'), info)
            if party==1:
                host = info['NetworkSettings']['Networks'][net]['IPAddress']
                if not host:
                    raise RuntimeError('missing holder network address')
        write_json(run/'driver-commands.json', driver_commands)
        for args, name in zip(driver_commands, names):
            log = (run/(name+'-driver.log')).open('w')
            log_handles.append(log)
            drivers.append(subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, text=True))
        # Wait for driver processes, not the intentionally persistent PID 1.
        # No repeated docker ps / inspect polling and no fixed grace-period sleep.
        deadline = time.monotonic()+design['timeout_per_pair_seconds']
        exits = [driver.wait(timeout=max(0.1, deadline-time.monotonic())) for driver in drivers]
        (run/'exit-codes.txt').write_text('\n'.join(map(str, exits))+'\n')
        if exits != [0, 0]:
            raise RuntimeError('party process failed: '+str(exits))
        return validate_pair(cell, run, design)
    finally:
        for name in names:
            result = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, timeout=20)
            (run/(name+'.log')).write_text(result.stdout+result.stderr)
            result = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True, timeout=20)
            (run/(name+'-inspect-end.json')).write_text(result.stdout)
        subprocess.run(['docker', 'rm', '-f', *names], capture_output=True, timeout=30)
        subprocess.run(['docker', 'network', 'rm', net], capture_output=True, timeout=30)
        for driver in drivers:
            try:
                driver.wait(timeout=5)
            except subprocess.TimeoutExpired:
                driver.kill()
                driver.wait()
        for log in log_handles:
            log.close()


def run():
    if sys.platform != 'linux':
        raise RuntimeError('run with the WSL launcher; do not use native Windows Docker')
    import fcntl
    lock = (JOB/'job.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (JOB/'status.json').exists():
        raise RuntimeError('job already attempted; inspect failure/completion, do not overwrite')
    design = json.loads((JOB/'design.json').read_text())
    status = dict(state='STARTING', stage='preflight', current='checking frozen artifacts',
                  started_utc=utc(), updated_utc=utc(), pid=os.getpid(), completed=0,
                  total=design['runs'], preflight_completed=0, current_log='job.stdout.log')

    def update(**changes):
        status.update(changes, updated_utc=utc())
        write_json(JOB/'status.json', status)
        print(f'{status["updated_utc"]} {status["stage"]} {status["completed"]}/{status["total"]} {status["current"]}', flush=True)

    try:
        update()
        check_freeze()
        command(['docker', 'info'], timeout=30)
        active = command(['docker', 'ps', '--format', '{{.Names}}'], timeout=20).strip()
        if active:
            raise RuntimeError('other Docker containers are active; stop competing experiments first: '+active)
        if max(int(x) for x in design['cpu_set'].split('-')) >= os.cpu_count():
            raise RuntimeError('frozen CPU set not available')
        environment = dict(utc=utc(), cpu_count=os.cpu_count(), affinity=sorted(os.sched_getaffinity(0)),
                           loadavg=os.getloadavg(), uname=command(['uname', '-a']),
                           cpuinfo=Path('/proc/cpuinfo').read_text(),
                           meminfo=Path('/proc/meminfo').read_text(),
                           docker_version=command(['docker', 'version']),
                           docker_info=command(['docker', 'info']))
        write_json(JOB/'environment.json', environment)
        images = {}
        for backend, config in BACKENDS.items():
            target = config['target']
            log = JOB/f'build-{target}.log'
            update(state='RUNNING', stage='build', current=target, current_log=log.name)
            with log.open('w') as output:
                subprocess.run(['bash', 'apeq-docker/docker/build_image.sh', target], cwd=SOURCE,
                               stdout=output, stderr=subprocess.STDOUT, check=True, timeout=1800)
            image_info = json.loads(command(['docker', 'image', 'inspect', 'apeq/'+target]))[0]
            images[backend] = image_info['Id']
            write_json(JOB/f'image-{target}.json', image_info)
        write_json(JOB/'images.json', images)
        update(stage='input-tests', current='C++ private-input isolation and parser tests', current_log='input-tests.log')
        with (JOB/'input-tests.log').open('w') as output:
            subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                            '--mount', f'type=bind,src={SOURCE/"apeq-docker/docker/bench"},dst=/bench,readonly',
                            '--mount', f'type=bind,src={PAPER/"tools"},dst=/tests,readonly',
                            '--entrypoint', '/bin/sh', images['bit_ot'], '-c',
                            'g++ -std=c++17 -O2 -I/bench /tests/check_application_io_v5.cpp -o /tmp/check-input && /tmp/check-input'],
                           stdout=output, stderr=subprocess.STDOUT, check=True, timeout=120)
        for backend in BACKENDS:
            for workload, batch, network in [('edge', 8, 'lan'), ('b10000-r00', 10000, 'wan')]:
                cell = dict(backend=backend, batch=batch, network=network, rep=0,
                            workload=workload, run_id=str(uuid.uuid4()))
                update(stage='smoke', current=f'{backend}/{workload}/{network}', current_log='job.stdout.log')
                run_pair(cell, design, images, 'smoke')
                update(preflight_completed=status['preflight_completed']+1)
        check_freeze()
        schedule = json.loads((JOB/'schedule.json').read_text())
        for cell in schedule:
            update(stage='E1', current=f'{cell["backend"]}/b{cell["batch"]}/{cell["network"]}/r{cell["rep"]}',
                   current_run_id=cell['run_id'], current_log='job.stdout.log')
            result = run_pair(cell, design, images, 'runs')
            with (JOB/'completed.jsonl').open('a') as log:
                log.write(json.dumps(dict(run_id=cell['run_id'], checked_utc=utc(), correct=result['correct']))+'\n')
                log.flush()
                os.fsync(log.fileno())
            update(completed=status['completed']+1)
        check_freeze()
        validations = [JOB/'runs'/cell['run_id']/'validation.json' for cell in schedule]
        if len(validations)!=240 or not all(json.loads(p.read_text())['correct'] for p in validations):
            raise RuntimeError('final completeness check failed')
        write_json(JOB/'completion.json', dict(completed_utc=utc(), runs=240,
                   comparisons=sum(c['batch'] for c in schedule), preflight_pairs=8,
                   result_hashes={p.relative_to(JOB).as_posix():sha(p) for p in (JOB/'runs').rglob('*') if p.is_file()},
                   next_step='Run the independent audit, then prepare the separate E3 campaign.'))
        update(state='COMPLETED', stage='complete', current='E1 validated; ready for independent analysis', current_run_id=None)
    except BaseException as error:
        details = traceback.format_exc()
        if isinstance(error, subprocess.CalledProcessError):
            details += '\nSUBPROCESS STDOUT:\n'+str(error.stdout)+'\nSUBPROCESS STDERR:\n'+str(error.stderr)
        (JOB/'error.txt').write_text(details)
        update(state='FAILED', current=str(error), current_log='error.txt')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run', 'check-freeze'])
    args = parser.parse_args()
    {'prepare': prepare, 'run': run, 'check-freeze': check_freeze}[args.action]()
