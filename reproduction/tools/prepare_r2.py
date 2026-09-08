"""Freeze the 30-pair R2 schedule before collecting data; preserve the main harness."""
from pathlib import Path
import csv, hashlib, json, random
import run_application_v5 as source_audit
root=Path(__file__).resolve().parents[1]
workspace=root.parent
out=root/'experiments/paired-width-r2'
out.mkdir(parents=True, exist_ok=True)
assert not (out/'schedule.csv').exists(), 'Do not overwrite a frozen schedule'
harness=workspace/'apeq-docker/docker/run_all.sh'
prefix=harness.read_text().split('\nfor profile in $NETWORKS; do',1)[0]
linux=workspace.as_posix()
script_dir=linux+'/apeq-docker/docker'
prefix=prefix.replace('SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"',f'SCRIPT_DIR="{script_dir}"')
run_dir=linux+'/reproduction/experiments/paired-width-r2'
setup=f'''#!/usr/bin/env bash
export RESULTS="{run_dir}/r2-raw.csv"
export RUN_DIR="{run_dir}/party-runs"
exec > "{run_dir}/execution.log" 2>&1
date -u --iso-8601=seconds
docker context show
docker info > "{run_dir}/docker-info.txt"
docker image inspect apeq/apeq apeq/aby > "{run_dir}/image-inspect.json"
docker run --rm --entrypoint /bin/sh apeq/apeq -c 'nproc; uname -a; cat /sys/fs/cgroup/cpuset.cpus.effective; cat /sys/fs/cgroup/cpu.max; cat /proc/meminfo' > "{run_dir}/container-environment.txt"
'''
rng=random.Random(0x52320001)
rows=[]; calls=[]
for pair in range(30):
    order=['OLE','ABY-Yao']; rng.shuffle(order)
    for position,protocol in enumerate(order,1):
        rows.append(dict(pair=pair,position=position,protocol=protocol))
        args='apeq apeq/apeq ips_ole ole 127' if protocol=='OLE' else 'aby_eq apeq/aby n/a yao 128'
        calls += [f'echo "R2 pair={pair} position={position} protocol={protocol}"',
                  f'run_pair {args} 100 16 wan {pair} || exit 1']
with (out/'schedule.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)
(out/'run-r2.sh').write_text(setup+prefix+'\n'+'\n'.join(calls)+'\ndate -u --iso-8601=seconds\n',newline='\n')
manifest=dict(design='30 adjacent pairs, independently randomised within-pair order, 60 fresh sessions',
  expected_source_revision=source_audit.revision(source_audit.source_inputs()),
  schedule_seed='0x52320001',primary='Party B total_ms; paired difference OLE minus ABY-Yao',
  interval='Two-sided 95% Student t interval for the mean paired difference, df=29; fixed sample size',
  rule='Retain failures and stop for investigation; no sample extension for significance',
  settings=dict(batch=100,bits=16,network='WAN',rtt_ms=80,bandwidth_mbps=100,n=1024,ell=255,rho=769,k=128,t=48),
  workload_seed='Existing harness SHA256 of protocol/backend/variant/configuration/repetition; independent across implementations',
  harness_sha256=hashlib.sha256(harness.read_bytes()).hexdigest())
(out/'design.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(out)
