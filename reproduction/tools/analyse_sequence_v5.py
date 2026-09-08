"""Read-only verification and sequence-level statistics for frozen E3."""
import math
import re
from collections import defaultdict
from statistics import mean, stdev
from analyse_application_v5 import load, digest, csv_rows, write_csv, PAPER, T9, args, RELEASE

JOB = PAPER/'experiments/sequence-v5'
TOOLS = RELEASE/'provenance/sequence-v5/tools' if args.archive_root else Path(__file__).parent


def main():
    done, design = load(JOB/'completion.json'), load(JOB/'design.json')
    assert load(JOB/'status.json')['state'] == 'COMPLETED'
    assert (done['sequences'], done['requests'], done['comparisons']) == (40, 800, 80000)
    for name, expected in done['result_hashes'].items():
        assert digest(JOB/name) == expected, name
    for name, expected in load(JOB/'data-sha256.json').items():
        assert digest(JOB/name) == expected, name
    # Independently establish E3's claimed lineage and public-manifest ordering.
    for rep in range(10):
        manifest = csv_rows(JOB/'data'/f'r{rep}/public/pairs.csv')
        assert [r['pair_id'] for r in manifest] == [f'p{i:06d}' for i in range(100)]
        for role in ('A','B'):
            original = csv_rows(PAPER/'experiments/application-v5/data'/f'b10000-r{rep:02d}/private-{role}/values.csv')
            for q in range(20):
                request = csv_rows(JOB/'data'/f'r{rep}/private-{role}/request-{q}.csv')
                assert [r['pair_id'] for r in request] == [r['pair_id'] for r in manifest]
                assert [r['value'] for r in request] == [r['value'] for r in original[q*100:(q+1)*100]]
    for name, expected in load(JOB/'freeze.json').items():
        path = (TOOLS/name[5:] if name.startswith('tool:') else
                JOB/'source-at-freeze/check_vole_session.cpp' if name.startswith('source-test:') else JOB/name)
        assert digest(path) == expected, name
    sources = load(JOB/'source-inputs.json')
    for p in (JOB/'source-at-freeze').rglob('*'):
        if p.is_file() and p.name != 'check_vole_session.cpp':
            assert digest(p) == sources[p.relative_to(JOB/'source-at-freeze').as_posix()]
    schedule = load(JOB/'schedule.json')
    assert len(schedule) == len({c['run_id'] for c in schedule}) == 40
    assert {p.name for p in (JOB/'runs').iterdir()} == {c['run_id'] for c in schedule}
    import json
    assert [json.loads(line)['run_id'] for line in (JOB/'completed.jsonl').read_text().splitlines()] == [c['run_id'] for c in schedule]
    requests, sequences, anomalies = [], [], []
    for cell in schedule:
        run = JOB/'runs'/cell['run_id']
        ev = load(run/'validation.json')
        assert ev['cell'] == cell and ev['correct'] and ev['comparisons'] == 2000
        launches = 1 if cell['mode'] == 'warm' else 20
        commands = load(run/'driver-commands.json')
        assert len(commands) == 2*launches
        assert len(list(run.glob('exit-*.json'))) == launches
        for launch in range(launches):
            assert load(run/f'exit-{launch}.json') == [0, 0]
            for party in range(2):
                command = commands[2*launch+party]
                assert command[command.index('--sequence-requests')+1] == str(20 if cell['mode']=='warm' else 1)
                assert command[command.index('--request-index')+1] == str(0 if cell['mode']=='warm' else launch)
        for role in ('A', 'B'):
            mounts = {m['Destination']: m for m in load(run/(role+'-inspect-start.json'))['Mounts']}
            assert set(mounts) == {'/input', '/public', '/out'}
            assert not mounts['/input']['RW'] and not mounts['/public']['RW']
            assert mounts['/input']['Source'].endswith(f'/data/r{cell["rep"]}/private-{role}')
            assert len(list((run/role/'metrics').glob('*.json'))) == 20
        assert not (run/'A/results').exists()
        seq = []
        for q in range(20):
            a, b = [load(run/role/'metrics'/f'request-{q}.json') for role in ('A','B')]
            assert ev['requests'][q]['parties'] == [a,b]
            for party, m in enumerate((a,b),1):
                expected = dict(run_id=cell['run_id']+f'-q{q}', source_revision=design['expected_source_revision'],
                                party=party, batch=100, input_bits=64, request_index=q,
                                sequence_requests=20 if cell['mode']=='warm' else 1,
                                correct=None, status='completed_unverified', rep=cell['rep'], network='wan',
                                protocol='apeq', nominal_kappa=128,
                                backend='bit_ot' if cell['backend']=='bit_ot' else 'ferret_vole',
                                variant='ole' if cell['backend']=='bit_ot' else 'vole_hash',
                                field_bits=127 if cell['backend']=='bit_ot' else 128)
                assert all(m[k] == v for k,v in expected.items())
                assert re.search(r'opened_connections=(\d+)',m['note']).group(1) == '1'
                assert 'fresh_crypto_setup_per_request' in m['note']
                for key in ('application_ms','setup_ms','online_ms','input_ms','output_ms','protocol_call_ms'):
                    assert math.isfinite(m[key]) and m[key] >= 0
                for direction in ('sent','recv'):
                    assert m['bytes_'+direction] == m['setup_bytes_'+direction]+m['online_bytes_'+direction]
            data = JOB/'data'/f'r{cell["rep"]}'
            ar,br,tr,actual = [csv_rows(p) for p in (data/f'private-A/request-{q}.csv',data/f'private-B/request-{q}.csv',data/f'truth/request-{q}.csv',run/f'B/results/request-{q}.csv')]
            assert len(ar) == len(br) == len(tr) == len(actual) == 100
            for aa,bb,tt,oo in zip(ar,br,tr,actual):
                assert aa['pair_id'] == bb['pair_id'] == tt['pair_id'] == oo['pair_id']
                assert tt['equal'] == oo['equal'] == str(int(int(aa['value'])==int(bb['value'])))
            row = dict(run_id=cell['run_id'],backend=cell['backend'],mode=cell['mode'],rep=cell['rep'],request=q)
            row.update({key:b[key] for key in ('application_ms','setup_ms','online_ms','input_ms','output_ms','protocol_call_ms')})
            row.update(sent_payload_bytes=a['bytes_sent']+b['bytes_sent'],A_peak_rss_kb=a['peak_rss_kb'],B_peak_rss_kb=b['peak_rss_kb'],delta_ab=a['bytes_sent']-b['bytes_recv'],delta_ba=b['bytes_sent']-a['bytes_recv'])
            if row['delta_ab'] or row['delta_ba']:
                anomalies.append({k:row[k] for k in ('run_id','request','delta_ab','delta_ba')})
            seq.append(row)
        requests.extend(seq)
        total = {k:cell[k] for k in ('run_id','backend','mode','rep')}
        for key in ('application_ms','setup_ms','online_ms','input_ms','output_ms','protocol_call_ms','sent_payload_bytes'):
            total[key] = sum(r[key] for r in seq)
        for key in ('A_peak_rss_kb','B_peak_rss_kb'):
            total[key] = max(r[key] for r in seq)
        total.update(connections=launches,host_wall_seconds=load(run/'wall-time.json')['seconds'])
        sequences.append(total)
    groups = defaultdict(list)
    for s in sequences:
        groups[s['backend'],s['mode']].append(s)
    assert len(groups)==4 and all({r['rep'] for r in g}==set(range(10)) for g in groups.values())
    summaries, contrasts = [], []
    for (backend,mode), group in sorted(groups.items()):
        summary = dict(backend=backend,mode=mode,n=10)
        for key in ('application_ms','setup_ms','online_ms','sent_payload_bytes','A_peak_rss_kb','B_peak_rss_kb','host_wall_seconds'):
            vals=[r[key] for r in group]
            summary[key+'_mean'],summary[key+'_sd']=mean(vals),stdev(vals)
        summaries.append(summary)
    for backend in ('bit_ot','vole_hash'):
        warm,cold=[sorted(groups[backend,mode],key=lambda r:r['rep']) for mode in ('warm','cold')]
        differences=[w['application_ms']-c['application_ms'] for w,c in zip(warm,cold)]
        delta,half=mean(differences),T9*stdev(differences)/math.sqrt(10)
        contrasts.append(dict(backend=backend,n=10,warm_minus_cold_ms=delta,ci95_low=delta-half,ci95_high=delta+half))
    audit=dict(sequences=40,requests=len(requests),party_records=2*len(requests),comparisons=80000,false_pos=0,false_neg=0,
               checked_result_hashes=len(done['result_hashes']),no_exclusions=True,source_revision=design['expected_source_revision'],
               cold_connections=sum(s['connections'] for s in sequences if s['mode']=='cold'),
               warm_connections=sum(s['connections'] for s in sequences if s['mode']=='warm'),
               request_counter_discrepancies=anomalies,max_abs_directional_delta=max(abs(r[k]) for r in requests for k in ('delta_ab','delta_ba')))
    out=args.output_dir.resolve() if args.output_dir else JOB/'analysis'
    out.mkdir(parents=True, exist_ok=True)
    for name,rows in (('per-request',requests),('per-sequence',sequences),('cell-summary',summaries),('paired-contrasts',contrasts)):
        write_csv(out/(name+'.csv'),rows)
    (out/'audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    lines=['# E3: independent audit and sequence-level results','',f'40 sequences; 800 requests; 80,000 comparisons; zero errors; {len(done["result_hashes"])} result hashes verified.',
           'Cold: 400 connections. Warm: 20 connections. Each request creates fresh cryptographic material. No formal exclusions. Four short preflights excluded by design.',
           '', '| Backend | Mode | B application total (s), mean ± SD | Setup total (s) | Online total (s) | Sent payload (KiB) |', '|---|---|---:|---:|---:|---:|']
    for s in summaries:
        lines.append(f'| {s["backend"]} | {s["mode"]} | {s["application_ms_mean"]/1000:.4f} ± {s["application_ms_sd"]/1000:.4f} | {s["setup_ms_mean"]/1000:.4f} | {s["online_ms_mean"]/1000:.4f} | {s["sent_payload_bytes_mean"]/1024:.3f} |')
    lines += ['', 'Paired warm − cold differences (10 sequence pairs per backend; two-sided Student t, df=9):']
    for c in contrasts:
        lines.append(f'- {c["backend"]}: {c["warm_minus_cold_ms"]/1000:.4f} s; 95% CI [{c["ci95_low"]/1000:.4f}, {c["ci95_high"]/1000:.4f}] s.')
    lines += ['',f'Maximum absolute directional sent/received boundary discrepancy: {audit["max_abs_directional_delta"]} B; raw counters retained, no normalization. Payload sums A+B sends and excludes TCP/IP framing.',
              'Warm mode also retains the driver process. This comparison measures the implemented persistent-session policy; it cannot isolate TCP connection establishment from congestion/flow state, process-local state, or scheduling effects. It does not test base-OT caching, amortized correlation generation, concurrency, or authenticated production service throughput.',
              'The unit is the sum of 20 request-local application times, excluding process/container launch, offline truth checking, and fsync. RSS is the maximum process high-water mark within a sequence.']
    (out/'E3-results.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('\n'.join(lines).encode('ascii', errors='replace').decode('ascii'))


if __name__=='__main__':
    main()
