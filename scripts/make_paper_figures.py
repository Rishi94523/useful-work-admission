"""Build the manuscript's data figures from recorded results.

Outputs go to docs/paper/figures/ (not committed; rebuilt from this script).
Inputs are the local result ledgers named in STATUS.md. Every figure uses the
same exclusion rules as the recorded analyses: device reports without
visibility tracking are excluded, as are measurements overlapping a hidden
page.
"""
import json,math,sys,statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_priority_admission import DEVICES,REPLAY_S,PATIENCE_S,CORE_RATE,HONEST_EVERY_S
from scripts.evaluate_admission_amendment12 import OUT as CORRECTED, SEEDS
OUT=ROOT/'docs/paper/figures';OUT.mkdir(parents=True,exist_ok=True)
LR=ROOT/'local-research'
CLASSES=['budget','mid','flagship'];LABEL={'budget':'Budget phone','mid':'Mid-range','flagship':'Flagship'}
# One muted, colour-blind-safe set, fixed per device class across figures.
COLOR={'budget':'#c0504d','mid':'#4f81bd','flagship':'#2e7d32','unit':'#2e7d32','single':'#c0504d','sub':'#4f81bd'}
plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150,'savefig.bbox':'tight'})

def jsonl(path):return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]

def corrected_rows(kind):
 rows=jsonl(CORRECTED/'results.jsonl')
 assert len(rows)==1120 and len({r['job_key'] for r in rows})==1120,'Complete amendment-12 grid required'
 return [r for r in rows if r['grid']==kind]

def seed_spread(values):
 assert len(values)==len(SEEDS),'Missing seed in plotted cell'
 return statistics.mean(values),min(values),max(values)

def device_timing():
 """Latency shape on phones (amendment 11 runs, all three kinds interleaved in
 the same sessions). Each kind is scaled by its own per-device median, so the
 curves compare distribution shape; calibration error is excluded by design
 and reported separately in the text."""
 series={'unit':[],'single':[],'sub':[]}
 for f in sorted((LR/'device-timing-subpuzzle').glob('timing_*.json')):
  r=json.loads(f.read_text(encoding='utf-8'))
  if r.get('error'):continue
  kinds={'unit':[u['run_ms'] for u in r['units'] if u['mode']=='reuse' and not u.get('overlaps_hidden')]}
  for k in ('single','sub'):kinds[k]=[p['ms'] for p in r['puzzles'] if p['kind']==k and not p.get('overlaps_hidden')]
  for k,v in kinds.items():
   s_=sorted(v);m=s_[len(s_)//2] if len(s_)%2 else (s_[len(s_)//2-1]+s_[len(s_)//2])/2
   series[k]+=[t/m for t in v]
 fig,ax=plt.subplots(figsize=(3.4,2.4))
 names={'unit':'Docking unit','single':'Single puzzle','sub':'64-subpuzzle puzzle'}
 for k,v in series.items():
  s_=sorted(v);ax.step(s_,[1-(i+1)/len(s_) for i in range(len(s_))],where='post',color=COLOR[k],label='%s (n=%d)'%(names[k],len(s_)))
 ax.set_xscale('log');ax.set_yscale('log');ax.set_ylim(1/200,1.05)
 ax.axvline(2,color='0.6',lw=0.8,ls=':');ax.text(2.05,0.6,'2× median',color='0.4',fontsize=7)
 ax.set_xlabel('Time ÷ device median for that kind');ax.set_ylabel('Fraction slower than x')
 ax.legend(frameon=False,fontsize=7,loc='lower left');fig.savefig(OUT/'device_latency.pdf');plt.close(fig)
 return {k:len(v) for k,v in series.items()}

def served_vs_cores():
 """Newcomers served against attacker cores, with the predicted threshold."""
 rows=corrected_rows('patience')
 fig,axes=plt.subplots(1,2,figsize=(6.8,2.4),sharey=True)
 for ax,w in zip(axes,(4,8)):
  R=w/REPLAY_S
  for cls in CLASSES:
   cores=sorted({r['attacker_cores'] for r in rows if r['workers']==w and r['attacker_cores']>0})
   pts=[seed_spread([r['classes'][cls]['served'] for r in rows if r['workers']==w and r['attacker_cores']==c]) for c in cores]
   ax.plot(cores,[p[0] for p in pts],'o-',color=COLOR[cls],ms=3,label=LABEL[cls])
   ax.fill_between(cores,[p[1] for p in pts],[p[2] for p in pts],color=COLOR[cls],alpha=.14)
   t=(R-1/HONEST_EVERY_S)*DEVICES[cls]*PATIENCE_S/CORE_RATE
   ax.axvline(t,color=COLOR[cls],lw=0.8,ls='--')
  # Amendment 13: the same queue with proof-of-work verification, lowest-served class.
  pow_path=LR/'admission-amendment13-2026-09-28/results.jsonl'
  if pow_path.exists():
   prow=[r for r in jsonl(pow_path) if r.get('grid')=='patience' and r['workers']==w and r['attacker_cores']>0]
   pc=sorted({r['attacker_cores'] for r in prow})
   low=[min(sum(r['classes'][c]['served'] for r in prow if r['attacker_cores']==x)/max(1,sum(1 for r in prow if r['attacker_cores']==x)) for c in CLASSES) for x in pc]
   if pc:ax.plot(pc,low,color='0.25',lw=1.2,ls=':',marker='s',ms=2.5,label='Proof-of-work gate')
  ax.set_xscale('log');ax.set_xlabel('Attacker CPU cores');ax.set_title('%d verifier workers'%w,fontsize=9)
 axes[0].set_ylabel('Honest newcomers served');axes[0].legend(frameon=False,fontsize=7)
 fig.savefig(OUT/'served_vs_cores.pdf');plt.close(fig)

def trust_bootstrap():
 """Share of newcomers reaching trust under a 16-core attack: no attestation,
 then 90% attested at rising attacker token supply."""
 rows=[r for r in corrected_rows('bootstrap') if r['attacker_cores']==16]
 def pick(w,s,a,cls,lane):
  return seed_spread([r['groups'][cls+'/'+lane]['trusted'] for r in rows if r['workers']==w and r['attested_share']==s and r['attacker_tokens_per_s']==a])
 rates=[0,0.1,1,10];fig,axes=plt.subplots(1,2,figsize=(6.8,2.5),sharey=True)
 for ax,w in zip(axes,(4,8)):
  width=0.26
  for j,cls in enumerate(CLASSES):
   stats=[pick(w,0,0,cls,'anonymous')]+[pick(w,.9,a,cls,'attested') for a in rates]
   vals=[s[0] for s in stats]
   xs=[i+(j-1)*width for i in range(len(vals))]
   ax.bar(xs,vals,width,color=COLOR[cls],label=LABEL[cls],
          yerr=[[s[0]-s[1] for s in stats],[s[2]-s[0] for s in stats]],capsize=2,error_kw={'elinewidth':.7})
   for x,v in zip(xs,vals):
    if v<0.02:ax.text(x,0.02,'0',ha='center',fontsize=7,color=COLOR[cls])
  ax.axvline(0.5,color='0.7',lw=0.8)
  ax.set_xticks(range(5));ax.set_xticklabels(['None\nattested','0','0.1','1','10'],fontsize=8)
  ax.set_xlabel('Attacker tokens per second (90% attested)',fontsize=8);ax.set_title('%d verifier workers'%w,fontsize=9)
 axes[0].set_ylabel('Newcomers reaching trust')
 h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,frameon=False,fontsize=7,ncol=3,loc='upper center',bbox_to_anchor=(0.5,1.06))
 fig.savefig(OUT/'trust_bootstrap.pdf');plt.close(fig)

def design_space():
 """Verification cost per admission against leverage, for every measured workload."""
 path=LR/'inference-leverage-2026-09-28/results.json'
 if not path.exists():return
 rows=json.loads(path.read_text(encoding='utf-8'))
 names={'mnist-mlp':'MNIST MLP','mnist-cnn':'MNIST CNN','cifar-cnn':'CIFAR CNN','vgg11-bn':'VGG11','mnist-wide-mlp':'Wide MLP'}
 fig,ax=plt.subplots(figsize=(4.6,3.0))
 for r in rows:
  ax.plot(r['verify_eff_ms'],r['leverage_8pct'],'o',color='#4f81bd',ms=5)
  off={'mnist-cnn':(-44,3),'cifar-cnn':(4,4),'vgg11-bn':(4,-9)}.get(r['model'],(4,3))
  ax.annotate(names[r['model']],(r['verify_eff_ms'],r['leverage_8pct']),textcoords='offset points',xytext=off,fontsize=6.5,color='#4f81bd')
 native=LR/'native-dense-2026-09-28/summary.json'
 if native.exists():
  w=next(r for r in json.loads(native.read_text(encoding='utf-8'))['rows'] if r['model']=='mnist-wide-mlp' and r['batch']==1)
  ax.plot(w['verify_eff_ms'],w['leverage_8pct'],'o',color='#4f81bd',mfc='white',ms=5)
  ax.annotate('Wide MLP, native',(w['verify_eff_ms'],w['leverage_8pct']),textcoords='offset points',xytext=(-62,3),fontsize=6.5,color='#4f81bd')
 ax.plot(1520,4,'s',color='#2e7d32',ms=6);ax.annotate('Docking, newcomer bundle',(1520,4),textcoords='offset points',xytext=(-60,-12),fontsize=6.5,color='#2e7d32')
 ax.plot(152,10,'s',color='#2e7d32',ms=6,mfc='white');ax.annotate('Docking, trusted (p = 0.1)',(152,10),textcoords='offset points',xytext=(-20,-12),fontsize=6.5,color='#2e7d32')
 ax.plot(0.77e-3,0.25,'v',color='#c0504d',ms=6);ax.annotate('Proof of work\n(no useful output)',(0.77e-3,0.25),textcoords='offset points',xytext=(5,-4),fontsize=6.5,color='#c0504d')
 ax.axhline(1,color='0.6',lw=0.8,ls=':');ax.text(9e3,0.88,'leverage 1: verifying costs\nas much as computing',fontsize=6,color='0.4',va='top',ha='right')
 ax.axvspan(1e-4,10,ymin=(math.log10(4)-math.log10(0.2))/(math.log10(20)-math.log10(0.2)),color='#f2c14e',alpha=0.18,lw=0)
 ax.text(1.5e-4,12,'cheap to verify and high leverage:\nno measured workload',fontsize=6.5,color='#8a6d00')
 ax.set_xscale('log');ax.set_yscale('log');ax.set_xlim(1e-4,1e4);ax.set_ylim(0.2,20)
 ax.set_xlabel('Verifier time per admission (ms, log scale)');ax.set_ylabel('Leverage (log scale)')
 fig.savefig(OUT/'design_space.pdf');plt.close(fig)

if __name__=='__main__':
 print('device latency samples',device_timing());served_vs_cores();trust_bootstrap();design_space()
 print('figures in',OUT)
