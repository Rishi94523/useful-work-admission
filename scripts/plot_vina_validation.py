"""Measured resource and scientific results; separate policy-model panel."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10';R=ROOT/'docs/evaluation/vina_resources_2026-09-10'
resource=json.loads((R/'summary.json').read_text())['rows'];medium=json.loads((OUT/'medium_e32.json').read_text());fa=json.loads((ROOT/'docs/evaluation/vina_tasks_2026-09-10/summary.json').read_text())['e32_score_selected_rmsd_A']
labels=['FA10','HS90A','TRYB1'];normal=[fa['normal_pose']]+[r['normal_quality']['top_rmsd_A'] for r in medium];bounded=[fa['medium_pose']]+[r['medium_quality']['top_rmsd_A'] for r in medium]
if (OUT/'tutorial_decomposition.json').exists():
 t=json.loads((OUT/'tutorial_decomposition.json').read_text());labels.append('1iep');normal.append(t['normal_quality']['top_rmsd_A']);bounded.append(t['medium_quality']['top_rmsd_A'])
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,grid=plt.subplots(2,2,figsize=(12,9),layout='constrained');axs=grid.ravel();x=np.arange(3);old=[];new=[]
for target in ['fa10','hs90a','tryb1']:
 old.append(next(r['renderer_os_peak_working_set_bytes']/2**20 for r in resource if r['target']==target and r['variant']=='baseline'))
 variant='compact_single' if target=='fa10' else 'compact'
 new.append(next(r['renderer_os_peak_working_set_bytes']/2**20 for r in resource if r['target']==target and r['variant']==variant))
axs[0].bar(x-.18,old,.36,label='Original',color='#667085');axs[0].bar(x+.18,new,.36,label='Storage optimized',color='#13795b');axs[0].set_xticks(x,['FA10*','HS90A','TRYB1']);axs[0].set_ylabel('OS peak renderer working set (MiB)');axs[0].set_title('Measured Chrome memory');axs[0].legend(frameon=False)
x=np.arange(len(labels));axs[1].bar(x-.18,normal,.36,label='Normal E32',color='#667085');axs[1].bar(x+.18,bounded,.36,label='Many 256k runs',color='#13795b');axs[1].set_xticks(x,labels);axs[1].set_ylabel('Top-ranked crystal RMSD (Angstrom)');axs[1].set_title('Measured redocking, matched evaluations');axs[1].legend(frameon=False)
ranking=json.loads((OUT/'summary.json').read_text())['matched_ranking'];x=np.arange(len(ranking));axs[2].bar(x-.18,[r['normal_E8_auc'] for r in ranking],.36,label='Normal E8',color='#667085');axs[2].bar(x+.18,[r['medium_auc'] for r in ranking],.36,label='Matched medium runs',color='#13795b');axs[2].set_xticks(x,[r['target'].upper() for r in ranking]);axs[2].set_ylabel('ROC-AUC');axs[2].set_ylim(0,1.05);axs[2].axhline(.5,color='#b54708',linestyle=':',linewidth=1);axs[2].set_title('Ranking pilot: four actives + four decoys');axs[2].legend(frameon=False)
policy=json.loads((OUT/'deferred_policy.json').read_text())['deferred'];rs=[r for r in policy if r['identity_grant_cap']==20 and r['verdict_lag_admissions']==2 and r['audit_probability']<=.25];axs[3].plot([100*r['audit_probability'] for r in rs],[r['expected_bad_grants_exact'] for r in rs],'o-',color='#b54708');axs[3].set_xlabel('Deferred audit probability (%)');axs[3].set_ylabel('Expected consumed bad admissions');axs[3].set_title('Policy model: cap20, verdict lag2');axs[3].set_ylim(0,21)
fig.suptitle('Vina validation checkpoint: memory improves; security remains conditional',fontsize=14)
fig.supxlabel('*FA10 also avoids unused task copies. Individual desktop trials; source-conformer controls; low-risk curve is a model.',fontsize=9)
fig.savefig(OUT/'validation_summary.png',dpi=180);fig.savefig(OUT/'validation_summary.svg')
p=OUT/'validation_summary.svg';p.write_text('\n'.join(line.rstrip() for line in p.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8');print('figure saved')
