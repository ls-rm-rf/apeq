from pathlib import Path
import csv, hashlib, json, statistics as st
from scipy.stats import t
root=Path(__file__).resolve().parents[1]; out=root/'experiments/paired-width-r2'
rows=list(csv.DictReader((out/'r2-raw.csv').open()))
schedule=list(csv.DictReader((out/'schedule.csv').open()))
expected_revision=json.loads((out/'design.json').read_text()).get('expected_source_revision', 'tree-c4e099904ae3')
assert len(rows)==120 and all(r['status']=='ok' and r['correct']=='true' for r in rows)
b=[r for r in rows if r['party']=='B']
assert len(b)==60
for r,s in zip(b,schedule):
    assert r['rep']==s['pair'] and (r['protocol']=='apeq')==(s['protocol']=='OLE')
    assert r['git_commit']==expected_revision and r['batch_size']=='100' and r['input_bits']=='16'
    assert r['rtt_ms']=='80.000' and r['bandwidth_mbps']=='100.000'
    assert r['n_false_pos']=='0' and r['n_false_neg']=='0'
pairs=[]
for i in range(30):
    pair={r['protocol']:r for r in b if int(r['rep'])==i}; assert len(pair)==2
    ole=float(pair['apeq']['total_ms']); aby=float(pair['aby_eq']['total_ms'])
    order=[s['protocol'] for s in schedule if int(s['pair'])==i]
    pairs.append(dict(pair=i,first=order[0],second=order[1],ole_run_id=pair['apeq']['run_id'],aby_run_id=pair['aby_eq']['run_id'],ole_ms=ole,aby_ms=aby,difference_ms=ole-aby))
with (out/'pairs.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=pairs[0]); w.writeheader(); w.writerows(pairs)
ole=[r['ole_ms'] for r in pairs]; aby=[r['aby_ms'] for r in pairs]; d=[r['difference_ms'] for r in pairs]
half=float(t.ppf(.975,29))*st.stdev(d)/(30**.5)
result=dict(n_pairs=30,n_executions=60,ole_mean_ms=st.mean(ole),ole_sd_ms=st.stdev(ole),
  aby_mean_ms=st.mean(aby),aby_sd_ms=st.stdev(aby),difference_mean_ms=st.mean(d),difference_sd_ms=st.stdev(d),
  ci95_ms=[st.mean(d)-half,st.mean(d)+half],ole_lower_mean_pairs=sum(x<0 for x in d),
  ratio_of_means=st.mean(aby)/st.mean(ole),relative_mean_reduction=1-st.mean(ole)/st.mean(aby),
  false_positives=0,false_negatives=0,exclusions=0,
  source_revision='tree-c4e099904ae3',schedule_sha256=hashlib.sha256((out/'schedule.csv').read_bytes()).hexdigest())
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
sig=result['ci95_ms'][1]<0
interpretation=('The interval supports a lower mean for OLE in this campaign.' if sig else
  'This campaign does not establish a lower mean for OLE; the main claim is limited accordingly.')
tex=r'''\section{R2: Paired Confirmation at 16 Input Bits}\label{sec:r2}
Before collecting data, we fixed 30 adjacent pairs comparing the current OLE
configuration with ABY-Yao at 16 input bits, batch 100, 80\,ms RTT and
100\,Mbit/s. Within each pair the implementation order was randomised using
schedule seed \texttt{0x52320001}. Each execution starts new parties and performs
fresh setup; 60 executions produce 120 party rows. The primary endpoint is Party
B's setup-inclusive total time, with paired difference
$d_j=T_{\mathrm{OLE},j}-T_{\mathrm{ABY},j}$ and interval
$\bar d\pm t_{0.975,29}s_d/\sqrt{30}$. We do not extend the sample to obtain
statistical significance. The interval assumes independent pair differences and
uses the usual Student approximation; it cannot eliminate shared-host effects.

The unchanged harness generates workload seeds independently across implementations
from protocol identity, parameters and repetition. Thus pairing controls adjacent
measurement time, not identical input vectors. Both rows use source revision
\texttt{tree-c4e099904ae3}. The WSL Docker containers again see ten logical
processors in \texttt{cpuset=0-9}, shared by the parties with no CPU quota.
No builds, attack verification or PDF compilation ran during collection.
The actual order matches the frozen schedule. All executions completed with
zero equality errors and no exclusions. The raw record is retained; ABY receive
normalisation is applied to a separate copy and changes no timing. The resulting
120-row record passes the standard structural validator.
'''
tex+=r'\begin{table}[t]\centering\caption{R2 Party B total time and paired difference, in milliseconds. Each implementation has 30 fresh sessions. The interval is for the mean paired difference, not each implementation separately.}\label{tab:r2}\begin{tabular}{lrr}\toprule Endpoint & Mean & Sample SD\\\midrule'+'\n'
tex+=f"APEQ (OLE) & {st.mean(ole):.2f} & {st.stdev(ole):.2f}"+r'\\'+'\n'
tex+=f"ABY-Yao & {st.mean(aby):.2f} & {st.stdev(aby):.2f}"+r'\\'+'\n'
tex+=f"OLE minus ABY-Yao & {st.mean(d):.2f} & {st.stdev(d):.2f}"+r'\\\bottomrule\end{tabular}\end{table}'+'\n'
tex+=f"The paired mean difference is ${st.mean(d):.2f}$ ms, with a 95\\% interval\n$[{st.mean(d)-half:.2f},{st.mean(d)+half:.2f}]$ ms. OLE is faster in\n{sum(x<0 for x in d)} of 30 pairs. The ratio of the two sample means is\n${st.mean(aby)/st.mean(ole):.3f}\\times$, a {100*(1-st.mean(ole)/st.mean(aby)):.2f}\\% reduction relative to ABY-Yao.\n"+interpretation+r'''
This is a separate measurement campaign from the frozen main-matrix cell,
which remains $704.73\pm18.20$ ms for OLE and $730.26\pm8.34$ ms for ABY-Yao
(ten sessions each). The new evidence concerns one configuration and does not
establish equal concrete security or an advantage at other widths and environments.
'''
(root/'supplementary-r2.tex').write_text(tex,encoding='utf-8')
print(json.dumps(result,indent=2))
