"""Verify reseed-on-retry on the real scheduler (protocol amendment 3).

Reruns the deployed bundle-tier configurations from phase 2 against the
committed PoolAdmission with reseeding implemented in VinaPoolCampaign. No
counterfactual subclass is involved: every row uses the scheduler as committed.
Attack strategies, verdict sources and metrics are imported unchanged from
admission_economics_eval.
"""
import hashlib,json,os,random,shutil,sys
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import admission_economics_eval as E

OUT=ROOT/'local-research/adversarial-2026-09-23'
SEED=20260923

def grid():
 out=[({'q':1,'k':k},dict(q=1,k=k)) for k in (0,1,2,3,4)]
 out.append(({'q':1,'k':1,'strategy':'submit-regardless'},dict(q=1,k=1,adaptive=False)))
 for budget in (64000,128000):
  for mode in ('pool_only','pool_and_trace'):out.append(({'q':1,'partial_budget':budget,'commitment':mode},dict(q=1,k=0,partial=(budget,mode))))
 for k in (2,3):out.append(({'q':2,'k':k},dict(q=2,k=k)))
 return out

def run_one(item):
 label,params=item;key=E.key(label)
 rng=random.Random(int(hashlib.sha256((str(SEED)+'reseed'+key).encode()).hexdigest()[:16],16))
 work=ROOT/'tmp/adversarial/phase3'/hashlib.sha256(key.encode()).hexdigest()[:12];work.mkdir(parents=True,exist_ok=True)
 try:return {'config_key':key,**label,**E.bundle_attack(E.Verdicts(rng),work,**params)}
 finally:shutil.rmtree(work,ignore_errors=True)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 manifest={'protocol':E.digest(E.PROTOCOL),'runner':E.digest(Path(__file__)),'harness':E.digest(ROOT/'scripts/admission_economics_eval.py'),'phase1':E.digest(E.PHASE1),
  'scheduler':{f:E.digest(ROOT/'research'/f) for f in ('pool_admission.py','adaptive_admission.py','vina_pool_campaign.py','docking_campaign.py','whole_run_campaign.py')},
  'target_admissions':E.TARGET,'verdict_seed':SEED}
 mp=OUT/'phase3_manifest.json'
 if mp.exists():assert json.loads(mp.read_text())==manifest,'Immutable manifest changed: '+str(mp)
 else:mp.write_text(json.dumps(manifest,indent=2))
 ledger=OUT/'phase3.jsonl';items=grid()
 done={json.loads(s)['config_key'] for s in ledger.read_text().splitlines() if s.strip()} if ledger.exists() else set()
 todo=[i for i in items if E.key(i[0]) not in done]
 print('configurations: %d total, %d to run'%(len(items),len(todo)),flush=True)
 with ProcessPoolExecutor(max_workers=12) as pool:
  for f in as_completed([pool.submit(run_one,i) for i in todo]):
   r=f.result()
   with ledger.open('a') as h:h.write(json.dumps(r)+chr(10));h.flush();os.fsync(h.fileno())
   print(json.dumps(r),flush=True)
 print('PHASE3 COMPLETE',flush=True)

if __name__=='__main__':main()
