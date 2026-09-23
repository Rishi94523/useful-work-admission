"""Verify removal of the audit reveal on the real scheduler (protocol amendment 4).

The committed PoolAdmission now returns only a challenge identifier from
commit(), and the reseeding from amendment 3 remains in place. Trusted-tier
rows test S1-S3; bundle-tier rows test S4, that walking away never mattered
there. Strategies, verdicts and metrics are imported unchanged from
admission_economics_eval. An attacker's walk-away rule is still supplied, but
the scheduler no longer gives it anything to act on.
"""
import hashlib,json,os,random,shutil,sys
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import admission_economics_eval as E

OUT=ROOT/'local-research/adversarial-2026-09-23'
SEED=20260923

def grid():
 out=[]
 for policy in ('immediate','deferred'):
  for p in (0.02,0.05,0.1,0.25):
   for G in (1,3):out.append(({'tier':'trusted','policy':policy,'p':p,'G':G,'acquire':'honest'},'trusted',dict(policy=policy,p=p,G=G,acquire='honest')))
 for k in (1,2,3,4):out.append(({'tier':'bundle','q':1,'k':k},'bundle',dict(q=1,k=k)))
 return out

def run_one(item):
 label,kind,params=item;key=E.key(label)
 rng=random.Random(int(hashlib.sha256((str(SEED)+'reveal'+key).encode()).hexdigest()[:16],16))
 work=ROOT/'tmp/adversarial/phase4'/hashlib.sha256(key.encode()).hexdigest()[:12];work.mkdir(parents=True,exist_ok=True)
 fn=E.trusted_attack if kind=='trusted' else E.bundle_attack
 try:return {'config_key':key,**label,**fn(E.Verdicts(rng),work,**params)}
 finally:shutil.rmtree(work,ignore_errors=True)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 manifest={'protocol':E.digest(E.PROTOCOL),'runner':E.digest(Path(__file__)),'harness':E.digest(ROOT/'scripts/admission_economics_eval.py'),'phase1':E.digest(E.PHASE1),
  'scheduler':{f:E.digest(ROOT/'research'/f) for f in ('pool_admission.py','adaptive_admission.py','vina_pool_campaign.py','docking_campaign.py','whole_run_campaign.py')},
  'target_admissions':E.TARGET,'verdict_seed':SEED}
 mp=OUT/'phase4_manifest.json'
 if mp.exists():assert json.loads(mp.read_text())==manifest,'Immutable manifest changed: '+str(mp)
 else:mp.write_text(json.dumps(manifest,indent=2))
 ledger=OUT/'phase4.jsonl';items=grid()
 done={json.loads(s)['config_key'] for s in ledger.read_text().splitlines() if s.strip()} if ledger.exists() else set()
 todo=[i for i in items if E.key(i[0]) not in done]
 print('configurations: %d total, %d to run'%(len(items),len(todo)),flush=True)
 with ProcessPoolExecutor(max_workers=12) as pool:
  for f in as_completed([pool.submit(run_one,i) for i in todo]):
   r=f.result()
   with ledger.open('a') as h:h.write(json.dumps(r)+chr(10));h.flush();os.fsync(h.fileno())
   print(json.dumps(r),flush=True)
 print('PHASE4 COMPLETE',flush=True)

if __name__=='__main__':main()
