"""Standalone scientific plots, derived exclusively from checked evidence."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
s=json.loads((OUT/'science_wasm_summary.json').read_text());e=json.loads((OUT/'economics.json').read_text())
fig,ax=plt.subplots(1,3,figsize=(15,4.2),constrained_layout=True)
for cap,color in [(4000,'#2878a4'),(16000,'#cb6624')]:
    r=[x for x in s['quality'] if x['cap']==cap];ax[0].plot([x['runs'] for x in r],[x['roc_auc'] for x in r],marker='o',color=color,label=f'{cap:,} eval cap')
    ax[1].plot([x['runs'] for x in r],[x['redocking_selected_rmsd_A'] for x in r],marker='o',color=color,label=f'{cap:,} cap, selected')
ax[0].axhline(s['historical_uncapped_e1']['roc_auc'],ls='--',color='#555',label='Historical native uncapped E1');ax[0].set_ylabel('ROC-AUC (one 32-molecule pilot)');ax[0].set_title('Screening quality');ax[0].set_ylim(0,1)
ax[1].axhline(2,ls=':',color='#555',label='2 Å reference');ax[1].set_ylabel('Symmetry-aware RMSD, Å');ax[1].set_title('Redocking: score-selected pose')
if 'stock_default_refinement_e8_redocking' in s:ax[1].axhline(s['stock_default_refinement_e8_redocking']['rmsd_A'],ls='--',color='#437c53',label='Stock Vina E8 control')
for a in ax[:2]:a.set_xscale('log',base=2);a.set_xlabel('Independent runs per ligand');a.legend(fontsize=8);a.grid(alpha=.2)
r=[x for x in e['tiers'] if x['cap']==16000 and x['runs']==16]
ax[2].plot([x['ligands'] for x in r],[x['molecular_ms']/1000 for x in r],marker='o',label='Client molecular search')
ax[2].plot([x['ligands'] for x in r],[next(z['replay_warm_ms'] for z in x['audit'] if z['q']==8)/1000 for x in r],marker='o',label='Server 8 replays, warm')
ax[2].plot([x['ligands'] for x in r],[next(z['total_ms'] for z in x['audit'] if z['q']==8)/1000 for x in r],marker='o',label='Server check + ligand setup')
ax[2].set_xscale('log',base=4);ax[2].set_xlabel('Ligands, 16 runs each');ax[2].set_ylabel('Seconds');ax[2].set_title('Replay economics: 16,000 cap');ax[2].legend(fontsize=8);ax[2].grid(alpha=.2)
fig.savefig(OUT/'whole_run_tradeoffs.png',dpi=180);fig.savefig(OUT/'whole_run_tradeoffs.svg');p=OUT/'whole_run_tradeoffs.svg';p.write_text('\n'.join(x.rstrip() for x in p.read_text().splitlines())+'\n')
