"""Build the manuscript's data figures from recorded results.

Outputs go to docs/paper/figures/ (not committed; rebuilt from this script).
Inputs are the local result ledgers named in STATUS.md. Every figure uses the
same exclusion rules as the recorded analyses: device reports without
visibility tracking are excluded, as are measurements overlapping a hidden
page.
"""
import json,math,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_priority_admission import DEVICES,REPLAY_S,PATIENCE_S,CORE_RATE,HONEST_EVERY_S
OUT=ROOT/'docs/paper/figures';OUT.mkdir(parents=True,exist_ok=True)
LR=ROOT/'local-research'
CLASSES=['budget','mid','flagship'];LABEL={'budget':'Budget phone','mid':'Mid-range','flagship':'Flagship'}
# One muted, colour-blind-safe set, fixed per device class across figures.
COLOR={'budget':'#c0504d','mid':'#4f81bd','flagship':'#2e7d32','unit':'#2e7d32','single':'#c0504d','sub':'#4f81bd'}
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150,'savefig.bbox':'tight'})

def jsonl(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def device_timing():
 """Latency on phones, each time scaled by its device's median warm unit."""
 series={'unit':[],'single':[],'sub':[]}
 for f in sorted((LR/'device-timing').glob('timing_*.json'))+sorted((LR/'device-timing-subpuzzle').glob('timing_*.json')):
  r=json.loads(f.read_text(encoding='utf-8'))
  if 'visibility' not in r or r.get('error'):continue
  warm=sorted(u['run_ms'] for u in r['units'] if u['mode']=='reuse' and not u.get('overlaps_hidden'));m=warm[len(warm)//2] if len(warm)%2 else (warm[len(warm)//2-1]+warm[len(warm)//2])/2
  if f.parent.name=='device-timing':series['unit']+= [t/m for t in warm]
  for p in r['puzzles']:
   if not p.get('overlaps_hidden'):series[p.get('kind','single')].append(p['ms']/m)
 fig,ax=plt.subplots(figsize=(3.4,2.4))
 names={'unit':'Docking unit','single':'Single puzzle','sub':'64-subpuzzle puzzle'}
 for k,v in series.items():
  if not v:continue
  s=sorted(v);ax.step(s,[1-(i+1)/len(s) for i in range(len(s))],where='post',color=COLOR[k],label='%s (n=%d)'%(names[k],len(s)))
 ax.set_xscale('log');ax.set_yscale('log');ax.set_ylim(1/300,1.05)
 ax.axvline(2,color='0.6',lw=0.8,ls=':');ax.text(2.05,0.6,'2× median',color='0.4',fontsize=7)
 ax.set_xlabel('Time ÷ device median unit time');ax.set_ylabel('Fraction slower than x')
 ax.legend(frameon=False,fontsize=7,loc='lower left');fig.savefig(OUT/'device_latency.pdf');plt.close(fig)
 return {k:len(v) for k,v in series.items()}

def served_vs_cores():
 """Newcomers served against attacker cores, with the predicted threshold."""
 rows=jsonl(LR/'priority-admission-2026-09-24-patience/results.jsonl')
 fig,axes=plt.subplots(1,2,figsize=(6.8,2.4),sharey=True)
 for ax,w in zip(axes,(4,8)):
  R=w/REPLAY_S
  for cls in CLASSES:
   pts=sorted((r['attacker_cores'],r['classes'][cls]['served']) for r in rows if r['workers']==w and r['attacker_cores']>0)
   ax.plot([p[0] for p in pts],[p[1] for p in pts],'o-',color=COLOR[cls],ms=3,label=LABEL[cls])
   t=(R-1/HONEST_EVERY_S)*DEVICES[cls]*PATIENCE_S/CORE_RATE
   ax.axvline(t,color=COLOR[cls],lw=0.8,ls='--')
  ax.set_xscale('log');ax.set_xlabel('Attacker CPU cores');ax.set_title('%d verifier workers'%w,fontsize=9)
 axes[0].set_ylabel('Honest newcomers served');axes[0].legend(frameon=False,fontsize=7)
 fig.savefig(OUT/'served_vs_cores.pdf');plt.close(fig)

def trust_bootstrap():
 """Share of newcomers reaching trust under a 16-core attack: no attestation,
 then 90% attested at rising attacker token supply."""
 rows=[r for r in jsonl(LR/'attested-admission-2026-09-25/bootstrap/results.jsonl') if r['attacker_cores']==16]
 pick=lambda w,s,a:next(r for r in rows if r['workers']==w and r['attested_share']==s and r['attacker_tokens_per_s']==a)
 rates=[0,0.1,1,10];fig,axes=plt.subplots(1,2,figsize=(6.8,2.5),sharey=True)
 for ax,w in zip(axes,(4,8)):
  width=0.26
  for j,cls in enumerate(CLASSES):
   vals=[pick(w,0,0)['groups'][cls+'/anonymous']['trusted']]+[pick(w,0.9,a)['groups'][cls+'/attested']['trusted'] for a in rates]
   xs=[i+(j-1)*width for i in range(len(vals))]
   ax.bar(xs,vals,width,color=COLOR[cls],label=LABEL[cls])
   for x,v in zip(xs,vals):
    if v<0.02:ax.text(x,0.02,'0',ha='center',fontsize=7,color=COLOR[cls])
  ax.axvline(0.5,color='0.7',lw=0.8)
  ax.set_xticks(range(5));ax.set_xticklabels(['None\nattested','0','0.1','1','10'],fontsize=8)
  ax.set_xlabel('Attacker tokens per second (90% attested)',fontsize=8);ax.set_title('%d verifier workers'%w,fontsize=9)
 axes[0].set_ylabel('Newcomers reaching trust')
 h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,frameon=False,fontsize=7,ncol=3,loc='upper center',bbox_to_anchor=(0.5,1.06))
 fig.savefig(OUT/'trust_bootstrap.pdf');plt.close(fig)

if __name__=='__main__':
 print('device latency samples',device_timing());served_vs_cores();trust_bootstrap()
 print('figures in',OUT)
