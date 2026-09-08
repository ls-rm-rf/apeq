"""Generate V5 tables/plots only from independently audited summary CSVs."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

P=Path(__file__).resolve().parents[1]
OUT=P/'generated'
OUT.mkdir(parents=True, exist_ok=True)
def rows(rel):
    with (P/rel).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))
e1=rows('experiments/application-v5/analysis/cell-summary.csv')
e3=rows('experiments/sequence-v5/analysis/cell-summary.csv')
ci=rows('experiments/application-v5/analysis/paired-contrasts.csv')
names={'bit_ot':'bit-OT','vole_hash':'VOLE','lu':'Lu','aby_yao':'ABY-Yao'}
order=list(names)
lookup={(r['network'],int(r['batch']),r['backend']):r for r in e1}
seq={(r['backend'],r['mode']):r for r in e3}
def val(r,key): return float(r[key])
def pm(r,key,scale=1,dec=2):
    return f'${val(r,key+"_mean")/scale:.{dec}f}\\pm{val(r,key+"_sd")/scale:.{dec}f}$'
text=[r'\begin{table*}[t]\centering\small',
      r'\caption{E1 B application time (ms, mean $\pm$ sample SD) over ten fresh executions per cell. All rows use 64-bit private files. Nominal security settings do not certify identical concrete guarantees across backends.}',
      r'\label{tab:e1-app}\begin{tabular}{llrrrr}\toprule',
      r'Link & Batch & bit-OT & VOLE & Lu & ABY-Yao\\\midrule']
for network in ('lan','wan'):
    for batch in (100,1000,10000):
        text.append(f'{network.upper()} & {batch:,} & '+' & '.join(pm(lookup[network,batch,b],'application_ms') for b in order)+r'\\')
text += [r'\bottomrule\end{tabular}\end{table*}']
(OUT/'main-v5-e1-table.tex').write_text('\n'.join(text)+'\n')
text=[r'\begin{table}[t]\centering\small',
      r'\caption{E3 B application time summed over 20 requests (seconds, mean $\pm$ sample SD over ten independent sequences). Fresh cryptographic setup is included in both policies.}',
      r'\label{tab:e3-app}\begin{tabular}{lrr}\toprule',r'Backend & Cold & Warm\\\midrule']
for backend in order[:2]:
    text.append(names[backend]+' & '+' & '.join(pm(seq[backend,m],'application_ms',1000,3) for m in ('cold','warm'))+r'\\')
text += [r'\bottomrule\end{tabular}\end{table}']
(OUT/'main-v5-e3-table.tex').write_text('\n'.join(text)+'\n')
text=[]
for network in ('lan','wan'):
    text += [r'\begin{table}[htbp]\centering\small',
             '\\caption{E1 '+network.upper()+r' diagnostic phase times (ms, mean $\pm$ sample SD); payload is A+B sent KiB. Ten executions per cell.}',
             r'\begin{tabular}{llrrr}\toprule',r'Batch & Backend & Setup & Online & Payload (KiB)\\\midrule']
    for batch in (100,1000,10000):
        for backend in order:
            r=lookup[network,batch,backend]
            text.append(f'{batch:,} & {names[backend]} & '+pm(r,'setup_ms')+' & '+pm(r,'online_ms')+f' & {val(r,"sent_payload_bytes_mean")/1024:,.2f}'+r'\\')
    text += [r'\bottomrule\end{tabular}\end{table}']
text += [r'\begin{table}[htbp]\centering\small',
         r'\caption{All 18 E1 paired application-time contrasts, in ms. Each compares an alternative with bit-OT at the same batch/link; ten pairs, two-sided 95\% Student $t$ intervals, df=9.}',
         r'\begin{tabular}{ll l rr}\toprule',r'Link & Batch & Alternative & Mean difference & 95\% interval\\\midrule']
for r in ci:
    label=names[r['contrast'].split(' minus ')[0]]
    text.append(f'{r["network"].upper()} & {int(r["batch"]):,} & {label} & {float(r["mean_ms"]):.2f} & $[{float(r["ci95_low_ms"]):.2f},{float(r["ci95_high_ms"]):.2f}]$'+r'\\')
text += [r'\bottomrule\end{tabular}\end{table}',r'\begin{table}[htbp]\centering\small',
         r'\caption{E3 sequence diagnostics: setup/online seconds summed over 20 requests, payload KiB, B maximum process RSS MiB, and host wall seconds including container/process setup. Entries are means over ten sequences; RSS is not a per-request independent sample.}',
         r'\begin{tabular}{llrrrrr}\toprule',r'Backend & Policy & Setup & Online & Payload & B RSS & Host wall\\\midrule']
for r in e3:
    text.append(f'{names[r["backend"]]} & {r["mode"]} & {val(r,"setup_ms_mean")/1000:.3f} & {val(r,"online_ms_mean")/1000:.3f} & {val(r,"sent_payload_bytes_mean")/1024:.3f} & {val(r,"B_peak_rss_kb_mean")/1024:.2f} & {val(r,"host_wall_seconds_mean"):.3f}'+r'\\')
text += [r'\bottomrule\end{tabular}\end{table}',r'\FloatBarrier']
(OUT/'supplementary-v5-data-tables.tex').write_text('\n'.join(text)+'\n')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.labelsize':8,'legend.fontsize':7,'pdf.fonttype':42})
colors=['#17619b','#c15a12','#37834f','#8662a8']
fig,axes=plt.subplots(2,1,figsize=(3.45,3.65),layout='constrained')
for ax,network in zip(axes,('lan','wan')):
    for backend,color,marker in zip(order,colors,('o','s','^','D')):
        rr=[lookup[network,b,backend] for b in (100,1000,10000)]
        ax.errorbar([100,1000,10000],[val(r,'application_ms_mean') for r in rr],
                    yerr=[val(r,'application_ms_sd') for r in rr],color=color,marker=marker,markersize=3,capsize=2,linewidth=1,label=names[backend])
    ax.set(xscale='log',yscale='log',ylabel='Application time (ms)',title=network.upper())
    ax.grid(True,which='major',alpha=.2)
    ax.set_xticks([100,1000,10000],['100','1,000','10,000'])
axes[0].legend(ncol=2,loc='upper left',frameon=False)
axes[1].set_xlabel('Pairs per request')
fig.savefig(OUT/'fig_application_v5.pdf',bbox_inches='tight');plt.close(fig)
fig,ax=plt.subplots(figsize=(3.45,2.5),layout='constrained')
rr=[seq[b,m] for b in order[:2] for m in ('cold','warm')]
x=np.arange(4); bottom=np.zeros(4)
total=np.array([val(r,'application_ms_mean')/1000 for r in rr])
setup=np.array([val(r,'setup_ms_mean')/1000 for r in rr])
online=np.array([val(r,'online_ms_mean')/1000 for r in rr])
for label,values,color in [('Setup',setup,'#17619b'),('Online',online,'#c15a12'),('Other',total-setup-online,'#a4abb3')]:
    assert all(values>=0)
    ax.bar(x,values,bottom=bottom,color=color,label=label,width=.63);bottom+=values
ax.errorbar(x,total,yerr=[val(r,'application_ms_sd')/1000 for r in rr],fmt='none',ecolor='black',capsize=3)
ax.set_xticks(x,['bit-OT\ncold','bit-OT\nwarm','VOLE\ncold','VOLE\nwarm'])
ax.set_ylabel('20-request total (s)');ax.set_ylim(0,28)
ax.legend(ncol=3,frameon=False,loc='upper left');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.savefig(OUT/'fig_sequence_v5.pdf',bbox_inches='tight');plt.close(fig)
print('Generated two main tables, four supplementary tables and two scientific figures from audited CSVs.')
