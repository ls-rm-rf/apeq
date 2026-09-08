from pathlib import Path
from collections import defaultdict, Counter
import csv, hashlib, json, statistics as st
from scipy.stats import t
root = Path(__file__).resolve().parents[1]
out = root/'experiments/implementation-v4'
rows = list(csv.DictReader((out/'v4-raw.csv').open()))
schedule = list(csv.DictReader((out/'schedule.csv').open()))
assert len(rows) == 338
assert all(r['status']=='ok' and r['correct']=='true' for r in rows)
assert all(r['n_false_pos']=='0' and r['n_false_neg']=='0' for r in rows if r['party']=='B')
names = {'ips_ole':'OLE-points-v2', 'bit_ot':'OLE-bit-OT', 'ferret_vole':'VOLE-sid-v2', 'n/a':'ABY-Yao'}
b = [r for r in rows if r['party']=='B']
for r,s in zip(b,schedule):
    assert names[r['backend']]==s['protocol']
    for field, key in [('batch_size','batch'),('input_bits','bits'),('network','network'),('rep','rep')]:
        assert r[field] == s[key]
commits = {r['git_commit'] for r in rows}
assert len(commits)==1
by_run=defaultdict(dict)
for r in rows: by_run[r['run_id']][r['party']]=r
normalised=[]; changes=[]
for r in rows:
    new=dict(r)
    if r['protocol']=='aby_eq':
        peer=by_run[r['run_id']]['B' if r['party']=='A' else 'A']
        for prefix in ['setup_','online_','']:
            receive=prefix+'bytes_recv'; send=prefix+'bytes_sent'
            if new[receive]!=peer[send]:
                changes.append(dict(run_id=r['run_id'],party=r['party'],field=receive,
                                    before=int(new[receive]),after=int(peer[send])))
            new[receive]=peer[send]
    normalised.append(new)
with (out/'v4-normalised.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(normalised)
with (out/'v4-timing-normalised.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader()
    w.writerows(r for r in normalised if r['batch_size']=='100')
(out/'normalisation-audit.json').write_text(json.dumps(changes,indent=2)+'\n')
cells=[]
for network in ['lan','wan']:
    for bits in [16,64]:
        for name in names.values():
            group=[r for r in b if r['batch_size']=='100' and r['network']==network and int(r['input_bits'])==bits and names[r['backend']]==name]
            assert len(group)==10
            cell=dict(network=network,bits=bits,protocol=name,n=10)
            for metric in ['setup_ms','online_ms','total_ms']:
                values=[float(r[metric]) for r in group]
                cell[metric]=st.mean(values); cell[metric+'_sd']=st.stdev(values)
            payload=[sum(int(x['bytes_sent']) for x in by_run[r['run_id']].values()) for r in group]
            cell['payload_bytes']=st.mean(payload);cell['payload_sd']=st.stdev(payload)
            cells.append(cell)
comparisons=[]
for bits in [16,64]:
    for name in ['OLE-points-v2','OLE-bit-OT']:
        selected=[r for r in b if r['batch_size']=='100' and r['network']=='wan' and int(r['input_bits'])==bits]
        d=[]
        for rep in range(10):
            g={names[r['backend']]:float(r['total_ms']) for r in selected if int(r['rep'])==rep}
            d.append(g[name]-g['ABY-Yao'])
        half=float(t.ppf(.975,9))*st.stdev(d)/(10**.5)
        comparisons.append(dict(bits=bits,protocol=name,difference_ms=st.mean(d),sd_ms=st.stdev(d),
                                ci95=[st.mean(d)-half,st.mean(d)+half]))
summary=dict(revision=next(iter(commits)),executions=169,timing_executions=160,boundary_executions=9,
    equality_tests=sum(int(r['batch_size']) for r in b),errors=0,exclusions=0,cells=cells,
    exploratory_paired_comparisons=comparisons,normalisation_changes=len(changes),
    maximum_normalisation_change=max(abs(c['before']-c['after']) for c in changes) if changes else 0)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
def cell(net,bits,name): return next(x for x in cells if (x['network'],x['bits'],x['protocol'])==(net,bits,name))
labels={'OLE-points-v2':'Packed OLE, sampled points', 'OLE-bit-OT':'Classical bit-OT OLE',
        'VOLE-sid-v2':'VOLE, session-bound hash', 'ABY-Yao':'ABY-Yao'}
main=r'''\subsection{Repaired interfaces and an OT-only reference}
\label{sec:eval-v4}
We separately evaluate the explicit-point OLE sampler, session-bound VOLE hash,
classical bit-OT reference and ABY-Yao. The fixed design has ten fresh sessions
per implementation at batch 100, widths 16/64 and both network profiles, with
random execution order within each width/network/repetition block. It adds
160 timing executions and nine boundary checks at $(b,w)=(1,1),(48,126),(49,126)$.
'''
main+=f"All {summary['equality_tests']:,} comparisons were correct, with no exclusions.\n"
main+=r'''Public-point generation/transport and nonce exchange are included in setup;
all other protocol costs are included in setup plus online time. The earlier
matrix and R2 are retained as historical measurements, not measurements of these
repaired interfaces. Supplement~\ref{supp-sec:v4-results} reports all 16 cells,
provenance, checks and the byte-normalisation audit.
\begin{table}[t]\centering\small
\caption{V4 WAN total time (ms, mean $\pm$ sample SD), batch 100, ten sessions per cell.
The bit-OT reference avoids the noisy-code assumption; sampled-point OLE still uses it.}
\label{tab:v4}\begin{tabular}{lrr}\toprule
Implementation & 16 bits & 64 bits\\\midrule
'''
for name in labels:
    a=cell('wan',16,name);b64=cell('wan',64,name)
    main+=f"{labels[name]} & ${a['total_ms']:.1f}\\pm{a['total_ms_sd']:.1f}$ & ${b64['total_ms']:.1f}\\pm{b64['total_ms_sd']:.1f}$"+r'\\'+'\n'
main+=r'\bottomrule\end{tabular}\end{table}'+'\n'
point=cell('wan',16,'OLE-points-v2'); ref=cell('wan',16,'ABY-Yao')
if point['total_ms']>=ref['total_ms']:
    main+=r'''The historical narrow 16-bit advantage over ABY-Yao does not survive as a
lower sample mean after the point-interface repair in this campaign. This is
why the original ranking is not carried over to revised software.
'''
else:
    main+=r'''The repaired packed path retains a lower 16-bit sample mean than ABY-Yao
in this campaign; however, their block-paired mean difference has a 95\% interval
of $[-24.24,0.71]$\,ms. This interval includes zero, so V4 does not confirm the
historical R2 advantage for the repaired implementation.
'''
main+=r'''The classical reference supplies a route whose reduction depends only on OT
and private randomness. It has lower sample means than packed OLE on both LAN
widths and at 16 bits on the WAN; their 64-bit WAN means are similar.
Thus the packed backend is not necessary to obtain the tested latency regime.
Its width-independent encoding trades assumptions and local work against the
reference's bit-dependent traffic. Neither its inclusion nor these measurements
certifies equal concrete strength of all compared libraries.
'''
(root/'main-v4-results.tex').write_text(main,encoding='utf-8')
supp=r'''\section{V4: Implementation Repairs and Reference Measurements}
\label{sec:v4-results}
The schedule was fixed before collection with seed \texttt{0x56340001}.
Four implementations were randomly ordered in each network/width/repetition
block. Each of the 16 timing cells has ten new sessions at batch 100. Nine
additional executions check 1-bit singleton input and 126-bit inputs at batches
48 and 49, covering the packed grouping boundary. These boundary runs are
correctness checks and are not pooled into timing cells. The same harness,
workload distribution and LAN/WAN profiles as the main matrix are used. No
build, rank computation or PDF compilation ran during collection.
'''
supp+=f"All 169 executions ({summary['equality_tests']:,} equality tests) passed with zero false accepts,\nzero false rejects and no exclusions. All rows use \\texttt{{{summary['revision']}}}.\n"
supp+=r'''The WSL Docker environment exposes ten shared logical CPUs without a CPU
quota; image manifests and effective CPU settings are retained. These are
synthetic aligned-input measurements, not an end-to-end record-linkage workload.
The bit-OT reference uses the same chosen-message IKNP/base-OT dependencies as
the packed driver; the VOLE backend remains the pinned silent-correlation stack.
The API security parameter is a library setting, not evidence of equal security
across the different assumptions.

\begin{table}[H]\centering\small
\caption{V4 complete timing matrix at batch 100. Times are Party B mean $\pm$
sample SD in milliseconds; payload is the sum of both sender counters in KiB.
Each cell has ten fresh sessions.}\label{tab:v4-complete}
\begin{tabular}{llrrrr}\toprule
Link / bits & Implementation & Setup & Online & Total & KiB\\\midrule
'''
for x in cells:
    short={'OLE-points-v2':'Packed points v2','OLE-bit-OT':'Bit-OT','VOLE-sid-v2':'VOLE sid v2','ABY-Yao':'ABY-Yao'}[x['protocol']]
    values=' & '.join(f"${x[m]:.2f}\\pm{x[m+'_sd']:.2f}$" for m in ['setup_ms','online_ms','total_ms'])
    supp+=f"{x['network'].upper()} / {x['bits']} & {short} & {values} & {x['payload_bytes']/1024:.2f}"+r'\\'+'\n'
supp+=r'\bottomrule\end{tabular}\end{table}'+'\n'
supp+=f"ABY receive normalisation changes {len(changes)} fields, by at most\n{summary['maximum_normalisation_change']} bytes. The raw and normalised records and every change\nare retained separately. Times and sender counters are unchanged.\n"
supp+=r'''The repaired drivers' counters are checked independently on both parties;
ABY's normalised mirrors remain structural checks. The historical packet-capture
audit is not presented as a packet-capture audit of V4.
The validator's variance and identical-row grouping was corrected after collection
to include backend identity, preventing bit-OT and packed OLE from being pooled.
The build-time validator is preserved alongside the corrected analysis version.
The 320 timing rows pass strict validation; the nine single-run boundary cases
are checked separately and are not treated as replicated estimates.

The core and real libOTe retrieval regression suites pass. New point-interface
checks cover wrong counts, cross-set and within-set duplicates, and a valid
zero-valued point with correct OLE reconstruction. Hash-interface checks use the
actual digest helper: all 512 single-bit changes to the two nonces and four
changes to width, batch, coordinate or field value produce a different tag;
identical context reproduces the tag. These 516 checks detect missing bindings,
not a cryptographic collision-resistance estimate. Fresh secret coins are used
in every measured run and are not derived from the public workload seed.

For transparency, the following exploratory block-paired differences compare
each OLE path with ABY-Yao on the WAN. Each interval is
$\bar d\pm t_{0.975,9}s_d/\sqrt{10}$. These are unadjusted pointwise 95\% intervals,
not simultaneous confidence claims across four comparisons; no sample was added
based on the outcomes.
\begin{table}[H]\centering\small
\caption{V4 exploratory mean differences, OLE minus ABY-Yao, in milliseconds.}
\begin{tabular}{llrr}\toprule
Bits & OLE path & Difference & 95\% interval\\\midrule
'''
for x in comparisons:
    supp+=f"{x['bits']} & {labels[x['protocol']]} & {x['difference_ms']:.2f} & [{x['ci95'][0]:.2f}, {x['ci95'][1]:.2f}]"+r'\\'+'\n'
supp+=r'\bottomrule\end{tabular}\end{table}'+'\n'
rank=json.loads((root/'experiments/bivariate-rank-v4/summary.json').read_text())
supp+=r'''\subsection{Exact bivariate target-rank checks}\label{sec:v4-rank}
For an affine target, we test $k\in\{4,8\}$, $e\in\{1,2,3\}$ and
$\tau\in\{0,2\}$, with $D=ek+1+\tau$ and
$N=\lfloor(D+1)^2/k\rfloor+1$. Five random instances per cell are checked over
each of $\mathbb F_{65537}$ and $\mathbb F_{2^{127}-1}$, using deterministic
seed \texttt{0x52414E4B}. All ranks use exact modular elimination. An independently
sampled right-hand side is solved to check target recovery rather than relying
only on rank differences.
'''
supp+=f"All {rank['full_target_recoveries']}/{rank['trials']} full transcripts recover both target\ncoefficients (target rank two). In all {rank['reduced_view_controls']} reduced-view controls,\nretaining only $R$ gives target rank one; an explicitly different target\n$P'(y)=P(y)+y-\\beta$ with a compensating change to $h_0$ produces exactly the same $R$.\n"
supp+=r'''This checks both recovering and private sides of the criterion. It is
finite-instance evidence for the specified masks, not a theorem that every
higher-degree repair fails under arbitrary parameters.
'''
(root/'supplementary-v4-results.tex').write_text(supp,encoding='utf-8')
print(json.dumps(summary,indent=2))
