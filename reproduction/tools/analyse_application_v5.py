"""Read-only audit of frozen E1 records and prespecified descriptive statistics."""
import csv
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive-root', type=Path, help='Directory containing experiments/application-v5 and experiments/sequence-v5')
parser.add_argument('--output-dir', type=Path, help='Write analysis separately from the input archive')
args = parser.parse_args()
RELEASE = Path(__file__).resolve().parents[2]
PAPER = args.archive_root.resolve() if args.archive_root else Path(__file__).resolve().parents[1]
TOOLS = RELEASE/'provenance/application-v5/tools' if args.archive_root else Path(__file__).parent
JOB = PAPER/'experiments/application-v5'
OUT = args.output_dir.resolve() if args.output_dir else JOB/'analysis'
T9 = 2.2621571627409915  # two-sided 95% Student t, df=9
LABELS = {'bit_ot': 'bit-OT', 'vole_hash': 'VOLE', 'lu': 'Lu', 'aby_yao': 'ABY-Yao'}


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    status, done, design = [load(JOB/name) for name in ('status.json', 'completion.json', 'design.json')]
    assert status['state'] == 'COMPLETED' and status['completed'] == done['runs'] == 240
    for name, expected in done['result_hashes'].items():
        assert digest(JOB/name) == expected, f'result changed: {name}'
    for name, expected in load(JOB/'data-sha256.json').items():
        assert digest(JOB/name) == expected, f'data changed: {name}'
    for name, expected in load(JOB/'freeze.json').items():
        path = TOOLS/name[5:] if name.startswith('tool:') else JOB/name
        assert digest(path) == expected, f'frozen artifact changed: {name}'
    for p in (JOB/'source-at-freeze').rglob('*'):
        if p.is_file():
            assert digest(p) == load(JOB/'source-inputs.json')[p.relative_to(JOB/'source-at-freeze').as_posix()]
    schedule = load(JOB/'schedule.json')
    assert len({c['run_id'] for c in schedule}) == 240
    assert {p.name for p in (JOB/'runs').iterdir()} == {c['run_id'] for c in schedule}
    journal = [json.loads(line) for line in (JOB/'completed.jsonl').read_text().splitlines()]
    assert [r['run_id'] for r in journal] == [c['run_id'] for c in schedule]
    rows, anomalies = [], []
    for cell in schedule:
        run = JOB/'runs'/cell['run_id']
        assert (run/'exit-codes.txt').read_text().split() == ['0', '0']
        evidence = load(run/'validation.json')
        assert evidence['cell'] == cell and evidence['correct'] and evidence['false_pos'] == evidence['false_neg'] == 0
        a, b = [load(run/role/'metrics.json') for role in ('A', 'B')]
        assert evidence['raw_party_metrics'] == [a, b]
        for party, metric in enumerate((a, b), 1):
            assert metric['source_revision'] == design['expected_source_revision']
            assert metric['run_id'] == cell['run_id'] and metric['batch'] == cell['batch'] and metric['party'] == party
            assert metric['correct'] is None and metric['status'] == 'completed_unverified'
            for name in ('input_ms', 'output_ms', 'application_ms', 'protocol_call_ms', 'setup_ms', 'online_ms'):
                assert math.isfinite(metric[name]) and metric[name] >= 0
            for direction in ('sent', 'recv'):
                assert metric['bytes_'+direction] == metric['setup_bytes_'+direction]+metric['online_bytes_'+direction]
            role = 'A' if party == 1 else 'B'
            mounts = {m['Destination']: m for m in load(run/(role+'-inspect-start.json'))['Mounts']}
            assert set(mounts) == {'/input', '/public', '/out'}
            assert not mounts['/input']['RW'] and not mounts['/public']['RW']
            assert mounts['/input']['Source'].endswith('/data/'+cell['workload']+'/private-'+role)
            assert mounts['/out']['Source'].endswith('/runs/'+cell['run_id']+'/'+role)
        # Recompute truth from private integer fields, not only saved labels.
        data = JOB/'data'/cell['workload']
        ai, bi, truth, output = [csv_rows(p) for p in (data/'private-A/values.csv', data/'private-B/values.csv',
                                                       data/'truth/equality.csv', run/'B/equality.csv')]
        assert len(ai) == len(bi) == len(truth) == len(output) == cell['batch']
        for ar, br, tr, actual in zip(ai, bi, truth, output):
            assert ar['pair_id'] == br['pair_id'] == tr['pair_id'] == actual['pair_id']
            expected = str(int(int(ar['value']) == int(br['value'])))
            assert tr['equal'] == actual['equal'] == expected
        assert not (run/'A/equality.csv').exists()
        delta_ab, delta_ba = a['bytes_sent']-b['bytes_recv'], b['bytes_sent']-a['bytes_recv']
        if delta_ab or delta_ba:
            anomalies.append(dict(run_id=cell['run_id'], backend=cell['backend'], delta_ab=delta_ab, delta_ba=delta_ba))
        rows.append(dict(run_id=cell['run_id'], backend=cell['backend'], network=cell['network'],
                         batch=cell['batch'], rep=cell['rep'], application_ms=b['application_ms'],
                         input_ms=b['input_ms'], output_ms=b['output_ms'], setup_ms=b['setup_ms'],
                         online_ms=b['online_ms'], protocol_call_ms=b['protocol_call_ms'],
                         other_protocol_ms=b['protocol_call_ms']-b['setup_ms']-b['online_ms'],
                         sent_payload_bytes=a['bytes_sent']+b['bytes_sent'],
                         receive_payload_bytes=a['bytes_recv']+b['bytes_recv'],
                         A_peak_rss_kb=a['peak_rss_kb'], B_peak_rss_kb=b['peak_rss_kb'],
                         payload_delta_ab=delta_ab, payload_delta_ba=delta_ba))
    groups = defaultdict(list)
    for row in rows:
        groups[row['network'], row['batch'], row['backend']].append(row)
    assert len(groups) == 24 and all(len(g) == 10 for g in groups.values())
    summaries, contrasts = [], []
    metrics = ['application_ms', 'setup_ms', 'online_ms', 'input_ms', 'output_ms', 'other_protocol_ms',
               'sent_payload_bytes', 'receive_payload_bytes', 'A_peak_rss_kb', 'B_peak_rss_kb']
    for (network, batch, backend), group in sorted(groups.items()):
        summary = dict(network=network, batch=batch, backend=backend, n=len(group))
        for metric in metrics:
            values = [r[metric] for r in group]
            summary[metric+'_mean'], summary[metric+'_sd'] = mean(values), stdev(values)
        summary['ms_per_comparison'] = summary['application_ms_mean']/batch
        summaries.append(summary)
    for network in ('lan', 'wan'):
        for batch in (100, 1000, 10000):
            reference = {r['rep']:r for r in groups[network, batch, 'bit_ot']}
            for backend in ('vole_hash', 'lu', 'aby_yao'):
                diffs = [r['application_ms']-reference[r['rep']]['application_ms'] for r in groups[network, batch, backend]]
                delta, sd = mean(diffs), stdev(diffs)
                margin = T9*sd/math.sqrt(10)
                contrasts.append(dict(network=network, batch=batch, contrast=backend+' minus bit_ot',
                                      n=10, mean_ms=delta, sample_sd_ms=sd,
                                      ci95_low_ms=delta-margin, ci95_high_ms=delta+margin))
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT/'per-run.csv', rows)
    write_csv(OUT/'cell-summary.csv', summaries)
    write_csv(OUT/'paired-contrasts.csv', contrasts)
    audit = dict(runs=240, comparisons=sum(r['batch'] for r in rows), false_pos=0, false_neg=0,
                 paired_party_records=480, data_checks='truth recomputed from both private integer fields',
                 frozen_result_hashes_checked=len(done['result_hashes']), cells=24, repeats_per_cell=10,
                 source_revision=design['expected_source_revision'], exclusions=0,
                 counter_differences=anomalies,
                 max_counter_difference=max([abs(r[k]) for r in rows for k in ('payload_delta_ab','payload_delta_ba')]),
                 uncertainty='18 descriptive paired t intervals; no multiplicity-adjusted discovery or tail-latency claim')
    (OUT/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    lines = ['# E1 应用实验核验与结果', '',
             f'240/240 次正式执行，480 份参与方指标，888000 对输入逐项重算并匹配输出；误报/漏报均为 0，无排除样本。核对 {len(done["result_hashes"])} 个冻结结果哈希。', '',
             '主指标是 B 的本地应用核验耗时，含读写、连接、完整初始化和协议收尾；不是完整企业业务耗时。下表单位 ms，均值 ± 样本 SD，每格 n=10。', '',
             '| 网络 | 配对数 | bit-OT | VOLE | Lu | ABY-Yao |', '|---|---:|---:|---:|---:|---:|']
    for network in ('lan', 'wan'):
        for batch in (100, 1000, 10000):
            selected = {s['backend']:s for s in summaries if s['network']==network and s['batch']==batch}
            lines.append('| '+network.upper()+' | '+str(batch)+' | '+' | '.join(
                f'{selected[b]["application_ms_mean"]:.2f} ± {selected[b]["application_ms_sd"]:.2f}' for b in LABELS)+' |')
    lines += ['', '## 预先指定的配对比较', '', '差值为该路线减 bit-OT；负值表示应用耗时较低。按 rep 配对，双侧 95% t 区间、df=9。18 个区间作描述使用，不以未校正的多重检验宣称发现。', '',
              '| 网络 | 配对数 | 比较 | 均值差 ms | 95% 区间 ms |', '|---|---:|---|---:|---|']
    for c in contrasts:
        lines.append(f'| {c["network"].upper()} | {c["batch"]} | {c["contrast"]} | {c["mean_ms"]:.2f} | [{c["ci95_low_ms"]:.2f}, {c["ci95_high_ms"]:.2f}] |')
    lines += ['', '## 审计口径', '',
              f'收发计数不完全对齐的执行共 {len(anomalies)} 次，最大方向差 {audit["max_counter_difference"]} B；全部原始计数保留，按后端列在 audit.json 中。通信汇总采用双方发送计数之和；不能将库计数称为 TCP 全链路流量，也不把接收差异悄悄归零。', '',
              '每条路线的安全假设与错误模型不同。正确性通过不是完整 128 位安全认证；这里不报告匹配质量/F1，也不把 10 次样本用于稳定 p95。旧中断、诊断和预检未混入正式矩阵。', '',
              '详细阶段时长、内存、双向发送计数见 cell-summary.csv；全部预定配对区间见 paired-contrasts.csv。E3 需要独立的顺序会话实现和设计，E1 重复进程不能替代它。']
    (OUT/'E1-results.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('\n'.join(lines[:15]))
    print(json.dumps({k:v for k,v in audit.items() if k!='counter_differences'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
