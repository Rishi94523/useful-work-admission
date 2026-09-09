"""Publication-style descriptive figures; no inference beyond the pilot samples."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path('docs/evaluation/adaptive_docking_2026-09-08')
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
e=json.loads((OUT/'economics_summary.json').read_text());tiers=e['shared_type_cache']['tiers'];names=['low','medium','high'];x=np.arange(3)
fig,axs=plt.subplots(1,2,figsize=(11,4.3),layout='constrained')
for dx,key,label,color in [(-.19,'client_total_ms','Client: search + preparation + protocol','#2678a5'),(.19,'total_server_with_db_ms','Server: replay + local IPC + database','#d6883a')]:
 values=[tiers[t][key]['median']/1000 for t in names];errors=np.array([[v-tiers[t][key]['min']/1000 for t,v in zip(names,values)],[tiers[t][key]['max']/1000-v for t,v in zip(names,values)]])
 axs[0].bar(x+dx,values,.36,label=label,color=color,yerr=np.maximum(0,errors),capsize=3)
axs[0].set(yscale='log',ylabel='Seconds (log scale)',xticks=x,xticklabels=[s.title() for s in names],title='Measured warm-tier economics (3 bundles each)');axs[0].legend(fontsize=8,loc='upper left');axs[0].grid(axis='y',alpha=.2)
loop=e['live']['adaptive_loop_calibrated.json']['scenarios']
for scenario,color in [('honest','#287d62'),('valid-spam','#aa552b'),('partial50','#7953a7')]:
 s=next(s for s in loop if s['name']==scenario);axs[1].plot(np.arange(len(s['sequence']))+1,[r['risk_after'] for r in s['sequence']],marker='o',ms=4,label=scenario,color=color)
for value in [15,35,60]:axs[1].axhline(value,color='gray',lw=.7,ls='--')
axs[1].set(xlabel='Completed challenge number',ylabel='Risk after outcome',title='Actual molecular loop; controlled arrival clock',ylim=(0,75));axs[1].legend(fontsize=9)
fig.suptitle('Adaptive whole-run docking with reusable preparation',fontsize=14)
fig.savefig(OUT/'adaptive_economics.png');fig.savefig(OUT/'adaptive_economics.svg');plt.close(fig)
if (OUT/'science_summary.json').exists():
 science=json.loads((OUT/'science_summary.json').read_text());targets=[t for t in science['targets'] if 'configs' in t];fig,axs=plt.subplots(2,len(targets),figsize=(12,7),layout='constrained',squeeze=False)
 for col,t in enumerate(targets):
  configs=t['configs'];labels=[str(c['runs'])+' × '+str(c['bound']//1000)+'k' if c['method']=='global' else '4 local' for c in configs];pos=np.arange(len(configs))
  for i,c in enumerate(configs):
   if c['ranking']:
    q=c['ranking'];axs[0,col].errorbar(i,q['auc'],yerr=[[q['auc']-q['auc_bootstrap95'][0]],[q['auc_bootstrap95'][1]-q['auc']]],fmt='o',capsize=4,color='#2678a5')
   else:axs[0,col].text(i,.08,'Incomplete',ha='center',va='bottom',rotation=90,fontsize=8,color='#a14b36')
   r=c['redocking'].get('independent')
   if r:axs[1,col].bar(i,r['selected_rmsd_A'],color='#2678a5',width=.6)
  baseline=t.get('stock_ranking')
  if baseline:axs[0,col].axhline(baseline['auc'],color='#d6883a',label='Stock E8',lw=1.5)
  elif t.get('stock_ranking_successes',0)>0:
   axs[0,col].axhspan(*t['stock_auc_missing_result_bounds'],color='#d6883a',alpha=.2,label='Stock timeout bounds');axs[0,col].legend(fontsize=8)
  axs[0,col].axhline(.65,color='gray',ls='--',lw=.8);axs[0,col].set(title=t['target'].upper(),ylabel='ROC-AUC',ylim=(0,1.05),xticks=pos,xticklabels=labels);axs[0,col].tick_params(axis='x',rotation=25)
  axs[1,col].axhline(2,color='gray',ls='--',lw=.8)
  for r in t.get('stock_redocking',[]):
   if r['conformer']=='independent':axs[1,col].axhline(r['rmsd_A'],color='#d6883a',label='Stock E8',lw=1.5)
  axs[1,col].set(ylabel='Score-selected redocking RMSD (Å)',xticks=pos,xticklabels=labels);axs[1,col].tick_params(axis='x',rotation=25)
 axs[0,0].legend(fontsize=9);fig.suptitle('Independent conformers: exploratory quality, 8 actives + 8 decoys per target\n16k/64k/256k bundles match nominal budgets; 4k and local are separate follow-ups/controls',fontsize=12)
 fig.savefig(OUT/'adaptive_science.png');fig.savefig(OUT/'adaptive_science.svg');plt.close(fig)
if (OUT/'converged_summary.json').exists():
 science=json.loads((OUT/'converged_summary.json').read_text());fig,axs=plt.subplots(2,3,figsize=(12,7),layout='constrained')
 for col,t in enumerate(science['targets']):
  configs=[c for c in t['configs'] if c['cap']!=1000000];labels=[str(c['runs'])+' × '+str(c['cap']//1000)+'k' for c in configs];pos=np.arange(len(configs))
  for i,c in enumerate(configs):
   q=c['ranking']
   if q:axs[0,col].errorbar(i,q['auc'],yerr=[[q['auc']-q['auc_bootstrap95'][0]],[q['auc_bootstrap95'][1]-q['auc']]],fmt='o',capsize=4,color='#287d62')
   else:axs[0,col].text(i,.08,'Incomplete',ha='center',rotation=90,fontsize=8)
   axs[1,col].bar(i,c['selected_rmsd_A'],color='#287d62',width=.6)
  if t['stock_ranking']:axs[0,col].axhline(t['stock_ranking']['auc'],color='#d6883a',label='Matched stock E8')
  elif t['stock_ranking_attempts']==16:
   axs[0,col].axhspan(*t['stock_auc_missing_result_bounds'],alpha=.2,color='#d6883a',label='Stock timeout bounds');axs[0,col].legend(fontsize=8)
  if 'rmsd_A' in t['stock']:axs[1,col].axhline(t['stock']['rmsd_A'],color='#d6883a')
  axs[0,col].axhline(.65,color='gray',ls='--',lw=.8);axs[0,col].set(title=t['target'].upper(),ylabel='ROC-AUC',ylim=(0,1.05),xticks=pos,xticklabels=labels)
  axs[1,col].axhline(2,color='gray',ls='--',lw=.8);axs[1,col].set(ylabel='Score-selected redocking RMSD (Å)',xticks=pos,xticklabels=labels)
 axs[0,0].legend(fontsize=9);fig.suptitle('Post-hoc converged-conformer correction: matched inputs and controls\nThree targets, 8 actives + 8 decoys each; intervals describe only this pilot',fontsize=12)
 fig.savefig(OUT/'converged_science.png');fig.savefig(OUT/'converged_science.svg');plt.close(fig)
if e.get('confidence_sweep'):
 rows=e['confidence_sweep']['rows'];qs=[r['q'] for r in rows];fig,axs=plt.subplots(1,2,figsize=(10,4.2),layout='constrained')
 axs[0].plot(qs,[100*r['pass_probability_90_percent'] for r in rows],'o-',color='#7953a7');axs[0].set(yscale='log',xlabel='Complete runs replayed (q)',ylabel='Attacker pass probability (%)',title='Exact bound: 230 correct records / 256');axs[0].grid(alpha=.2)
 vals=[r['server_ipc_wall_ms']['median']/1000 for r in rows];err=np.array([[v-r['server_ipc_wall_ms']['min']/1000 for v,r in zip(vals,rows)],[r['server_ipc_wall_ms']['max']/1000-v for v,r in zip(vals,rows)]])
 axs[1].errorbar(qs,vals,yerr=np.maximum(0,err),fmt='o-',capsize=4,color='#d6883a');axs[1].set(xlabel='Complete runs replayed (q)',ylabel='Server replay + local IPC (seconds)',title='Measured replay, median and range (n=3)');axs[1].grid(alpha=.2)
 fig.suptitle('Stronger sampling costs more replay; no fresh database timing in this sweep',fontsize=12)
 fig.savefig(OUT/'audit_confidence.png');fig.savefig(OUT/'audit_confidence.svg');plt.close(fig)
for name in ['adaptive_economics','adaptive_science','converged_science','audit_confidence']:
 path=OUT/(name+'.svg')
 if path.exists():path.write_text('\n'.join(line.rstrip() for line in path.read_text().splitlines())+'\n')
print('Saved adaptive figures')
