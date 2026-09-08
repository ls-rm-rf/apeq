"""Freeze the targeted implementation-validation design before data collection."""
from pathlib import Path
import csv, json, random
root = Path(__file__).resolve().parents[1]
ws = root.parent
out = root / 'experiments/implementation-v4'
out.mkdir(parents=True, exist_ok=True)
assert not (out / 'schedule.csv').exists()
linux = ws.as_posix()
prefix = (ws / 'apeq-docker/docker/run_all.sh').read_text().split('\nfor profile in $NETWORKS; do', 1)[0]
prefix = prefix.replace('SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"', f'SCRIPT_DIR="{linux}/apeq-docker/docker"')
spec = {
    'OLE-points-v2': 'apeq apeq/apeq ips_ole ole 127',
    'OLE-bit-OT': 'apeq apeq/apeq-ot bit_ot ole 127',
    'VOLE-sid-v2': 'apeq apeq/apeq-vole ferret_vole vole_hash 128',
    'ABY-Yao': 'aby_eq apeq/aby n/a yao 128',
}
rng = random.Random(0x56340001)
rows = []
for network in ['lan', 'wan']:
    for bits in [16, 64]:
        for rep in range(10):
            order = list(spec)
            rng.shuffle(order)
            for name in order:
                rows.append(dict(purpose='timing', protocol=name, batch=100, bits=bits, network=network, rep=rep))
for batch, bits in [(1, 1), (48, 126), (49, 126)]:
    for name in list(spec)[:3]:
        rows.append(dict(purpose='boundary', protocol=name, batch=batch, bits=bits, network='lan', rep=0))
with (out / 'schedule.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
run = f'{linux}/reproduction/experiments/implementation-v4'
setup = f'''#!/usr/bin/env bash
export RESULTS="{run}/v4-raw.csv"
export RUN_DIR="{run}/party-runs"
exec > "{run}/execution.log" 2>&1
date -u --iso-8601=seconds
docker info > "{run}/docker-info.txt"
docker run --rm --entrypoint /bin/sh apeq/apeq -c 'nproc; uname -a; cat /sys/fs/cgroup/cpuset.cpus.effective; cat /sys/fs/cgroup/cpu.max' > "{run}/environment.txt"
'''
calls = []
for row in rows:
    calls += [f'echo "V4 {row}"', f'run_pair {spec[row["protocol"]]} {row["batch"]} {row["bits"]} {row["network"]} {row["rep"]} || exit 1']
(out / 'run-v4.sh').write_text(setup + prefix + '\n' + '\n'.join(calls) + '\ndate -u --iso-8601=seconds\n', newline='\n')
(out / 'design.json').write_text(json.dumps(dict(seed='0x56340001', timing_executions=160, boundary_executions=9, repetitions=10,
    design='Random order of four implementations within each width/network/repetition block; fresh setup each execution',
    stop_rule='Fixed sample size; retain and investigate all failures; no significance-based extension',
    comparison='Party B total time; mean and sample SD; ABY receive normalization disclosed separately',
    provenance='New implementation revision only; historical main/R2/E2 rows are never replaced'), indent=2) + '\n')
print('Frozen 160 timing + 9 boundary executions')
