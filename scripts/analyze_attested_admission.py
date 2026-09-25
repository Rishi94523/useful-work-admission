"""Score the amendment 10 results against predictions A1-A6 as recorded."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.evaluate_priority_admission import DEVICES,REPLAY_S,PATIENCE_S,CORE_RATE,HONEST_EVERY_S
from scripts.evaluate_attested_admission import OUT

LAM=1/HONEST_EVERY_S
load=lambda exp:[json.loads(s) for s in (OUT/exp/'results.jsonl').read_text().splitlines() if s.strip()]
R=lambda r:r['workers']/REPLAY_S
threshold=lambda r,cls:max(0.0,R(r)-LAM-r['attacker_tokens_per_s'])*DEVICES[cls]*PATIENCE_S/CORE_RATE

def score(name,checks):
 bad=[c for c in checks if not c[0]]
 print('%s: %d/%d held'%(name,len(checks)-len(bad),len(checks)))
 for c in bad:print('  violated:',c[1])

def main():
 one=load('oneshot');boot=load('bootstrap')
 cell=lambda r:'w=%d cores=%g s=%g a=%g'%(r['workers'],r['attacker_cores'],r['attested_share'],r['attacker_tokens_per_s'])
 a1=[];a2=[];a3=[];a6=[]
 for r in one:
  lam_a=LAM*r['attested_share'];demand=lam_a+r['attacker_tokens_per_s']
  for k,g in r['groups'].items():
   cls,lane=k.split('/')
   if lane=='attested':
    if demand<=0.8*R(r):a1.append((g['served']>=0.9,'%s %s served %.2f'%(cell(r),k,g['served'])))
    if demand>=1.25*R(r):a2.append((g['served']<=R(r)/demand+0.1,'%s %s served %.2f bound %.2f'%(cell(r),k,g['served'],R(r)/demand+0.1)))
    a6.append((g['fallbacks']>0 or g['puzzle_s_total']==0,'%s %s paid %.1f s without fallback'%(cell(r),k,g['puzzle_s_total'])))
   else:
    if demand>=1.25*R(r):a2.append((g['served']<=0.2,'%s %s served %.2f'%(cell(r),k,g['served'])))
    if r['attested_share']<=0.5 and r['attacker_cores']>0 and g['users']>=20:
     t=threshold(r,cls)
     if r['attacker_cores']<t/2:a3.append((g['served']>=0.9,'%s %s served %.2f below half of %.2f cores'%(cell(r),k,g['served'],t)))
     elif r['attacker_cores']>2*t:a3.append((g['served']<=0.5,'%s %s served %.2f above twice %.2f cores'%(cell(r),k,g['served'],t)))
 score('A1 attested served at any CPU budget',a1);score('A2 saturated attested lane',a2)
 score('A3 anonymous threshold (R - lambda - a) r T',a3)
 prior={(p['workers'],p['attacker_cores']):p for p in (json.loads(s) for s in (ROOT/'local-research/priority-admission-2026-09-24-patience/results.jsonl').read_text().splitlines() if s.strip())}
 a4=[]
 for r in one:
  if r['attested_share']==0 and r['attacker_tokens_per_s']==0:
   p=prior[(r['workers'],r['attacker_cores'])]
   for cls in DEVICES:
    x=r['groups'][cls+'/anonymous']['served'];y=p['classes'][cls]['served']
    a4.append((abs(x-y)<=0.10,'%s %s %.2f vs 9b %.2f'%(cell(r),cls,x,y)))
 score('A4 inert lane matches 9b',a4);score('A6 attested pay no puzzle without fallback',a6)
 a5=[]
 for r in boot:
  if r['attacker_cores']!=16:continue
  for k,g in r['groups'].items():
   lane=k.split('/')[1];s,a=r['attested_share'],r['attacker_tokens_per_s']
   if s==0:a5.append((g['trusted']<=0.1,'%s %s trusted %.2f (lockout)'%(cell(r),k,g['trusted'])))
   elif lane=='anonymous':a5.append((g['trusted']<=0.1,'%s %s trusted %.2f'%(cell(r),k,g['trusted'])))
   elif a<=0.1:a5.append((g['trusted']>=0.9,'%s %s trusted %.2f'%(cell(r),k,g['trusted'])))
   elif a==10:a5.append((g['trusted']<=0.5,'%s %s trusted %.2f'%(cell(r),k,g['trusted'])))
 score('A5 trust bootstrap under 16 cores',a5)
 fb=sum(g['fallbacks'] for r in one for k,g in r['groups'].items() if k.endswith('attested'))
 att=sum(g['attempts'] for r in one for k,g in r['groups'].items() if k.endswith('attested'))
 print('E1 attested fallbacks: %d of %d attempts'%(fb,att))

if __name__=='__main__':main()
