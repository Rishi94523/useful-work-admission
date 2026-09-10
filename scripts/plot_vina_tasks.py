"""Plot completed aggregate results; native MC time is not browser latency."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10'
s=json.loads((OUT/'summary.json').read_text());fig,axes=plt.subplots(2,3,figsize=(14,8),layout='constrained')
for j,t in enumerate(s['targets']):
 for conf,style in [('source','o-'),('converged','s--')]:
  points=[(c['point'],r['rmsd_A']) for c in t['configs'] if c['method']=='normal' for r in c['redocking'] if r['conformer']==conf]
  if points:axes[0,j].plot(*zip(*points),style,label=conf)
 axes[0,j].axhline(2,color='gray',ls=':',label='2 Å reference');axes[0,j].set(xscale='log',xlabel='Accumulated normal runs',ylabel='Score-selected RMSD (Å)',title=t['target'].upper());axes[0,j].legend(fontsize=8)
 for method,marker in [('normal','o'),('matched','s'),('wallmatched','^')]:
  points=[(c['ranking_median_search_ms']/1000,c['ranking']['auc']) for c in t['configs'] if c['method']==method and c['ranking']]
  if points:axes[1,j].scatter(*zip(*points),marker=marker,label=method)
 if t['stock_subset_quality']:axes[1,j].axhline(t['stock_subset_quality']['auc'],ls=':',color='gray',label='downloaded stock E8 AUC')
 axes[1,j].set(xscale='log',ylim=(0,1.05),xlabel='Median native MC seconds / ligand',ylabel='ROC-AUC (4 active + 4 decoy)');axes[1,j].legend(fontsize=8)
fig.suptitle('Distributed Vina: aggregate quality pilot\nMatched = first normal run’s evaluation budget; wallmatched = closest available MC-time prefix',fontsize=12)
fig.savefig(OUT/'aggregate_quality.png',dpi=160);fig.savefig(OUT/'aggregate_quality.svg');plt.close(fig)
svg=OUT/'aggregate_quality.svg';svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
print('Saved aggregate quality figure')
