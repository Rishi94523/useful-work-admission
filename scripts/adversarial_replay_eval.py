"""Phase 1 of the adversarial evaluation: attacks judged by real molecular replay.

Earlier attack experiments supplied molecular verdicts from a model. Here every
verdict comes from re-executing the assigned unit with the frozen driver, or
from running the original Vina finalizer over a tampered pool. See
docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md.

Unit-level attacks, on a salted-hash sample of units from the preserved corpus:
  honest  the true task file; replay must match it exactly
  A1      substitution: another unit's valid result claimed for this unit
  A2      partial work: the unit genuinely searched with a quarter or half of
          its evaluation budget, judged by pool-only and by pool+trace commitment
  A3      cached replay: the true result resubmitted; replay accepts by design

Pool-level attacks, per corpus job, judged by the original finalizer:
  A8e     the best minimum of one unit given a falsely improved energy
  A8c     the best minimum of one unit translated by a small distance

Timing is measured in this process under a fixed worker count, so client and
verifier costs share load conditions. Campaign timings were taken under 14-way
contention and are not used as client costs.
"""
import hashlib,json,os,shutil,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run_published_matched import Worker,digest,ROOT

CORPUS=ROOT/'tmp/vina-published/matched_samebuild'
INPUTS=ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json'
OUT=ROOT/'local-research/adversarial-2026-09-23'
WORK=ROOT/'tmp/adversarial/phase1'
PROTOCOL=ROOT/'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'
SALT='adversarial-units-2026-09-23:'
UNITS_PER_JOB=3
CAP=256000
PARTIAL=(64000,128000)
ENERGY_DELTAS=(0.1,1.0,3.0)
SHIFTS=(0.1,0.5,2.0)
WORKERS=4

def save(p,x):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));os.replace(tmp,p)
def freeze(p,x):
 if p.exists():assert json.loads(p.read_text())==x,'Immutable manifest changed: '+str(p)
 else:save(p,x)
def read(p):return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []
def append(p,x):
 with p.open('a') as f:f.write(json.dumps(x)+'\n');f.flush();os.fsync(f.fileno())

def corpus_jobs():
 return sorted(m.parent for m in CORPUS.rglob('PRESERVED_FOR_ADVERSARIAL_EVAL') if (m.parent/'medium').is_dir())

def pick_units(job,n):
 key='/'.join(job.parts[-3:])
 return sorted(sorted(range(n),key=lambda i:hashlib.sha256(f'{SALT}{key}/{i}'.encode()).hexdigest())[:UNITS_PER_JOB])

def parse_record(line):
 """Split one pool record into energy, conformation tokens and coordinates.

 Layout per task_write: energy, then position(3), orientation(4) and torsions
 for the single ligand, then the coordinate count and 3*count coordinates. The
 torsion count is not stored, so it is solved from the record length.
 """
 tok=line.split()
 for tors in range(len(tok)):
  head=1+7+tors
  if head>=len(tok):break
  try:count=int(tok[head])
  except ValueError:continue
  if len(tok)==head+1+3*count:
   return tok[0],tok[1:head],tok[head],tok[head+1:]
 raise ValueError('Unrecognised task record layout')

def best_index(lines):
 return min(range(1,len(lines)),key=lambda k:float(lines[k].split()[0]))

def tamper_energy(text,delta):
 lines=text.splitlines();k=best_index(lines);e,conf,count,coords=parse_record(lines[k])
 lines[k]=' '.join([repr(float(e)-delta),*conf,count,*coords]);return '\n'.join(lines)+'\n'

def tamper_shift(text,dx):
 lines=text.splitlines();k=best_index(lines);e,conf,count,coords=parse_record(lines[k])
 conf=list(conf);conf[0]=repr(float(conf[0])+dx)
 coords=[repr(float(c)+dx) if j%3==0 else c for j,c in enumerate(coords)]
 lines[k]=' '.join([e,*conf,count,*coords]);return '\n'.join(lines)+'\n'

def final_score(pose):
 for l in Path(pose).read_text().splitlines():
  if 'VINA RESULT' in l:return float(l.split(':')[1].split()[0])
 raise ValueError('No score in '+str(pose))

def job_eval(job,targets):
 tname,lid,seed=job.parts[-3],job.parts[-2],int(job.parts[-1])
 t=targets[tname];l=next(x for x in t['ligands'] if x['id']==lid)
 med=job/'medium';n=len(list(med.glob('*.task')))
 folder=WORK/tname/lid/str(seed);shutil.rmtree(folder,ignore_errors=True);folder.mkdir(parents=True)
 rows=[];base={'target':tname,'id':lid,'label':l['label'],'seed':seed,'units':n}
 w=Worker(t,l,folder)
 try:
  for i in pick_units(job,n):
   truth=(med/f'{i}.task').read_bytes();truth_trace=(med/f'{i}.task.trace').read_bytes()
   out=folder/f'replay_{i}';out.mkdir()
   begin=time.perf_counter();w.run(1,i,seed,n,CAP,out,folder/'unused.pdbqt');replay_ms=(time.perf_counter()-begin)*1000
   replayed=(out/f'{i}.task').read_bytes();replayed_trace=(out/f'{i}.task.trace').read_bytes()
   ingest=time.perf_counter();hashlib.sha256(truth).digest();ingest_ms=(time.perf_counter()-ingest)*1000
   rows.append({**base,'unit':i,'attack':'honest','accepted':replayed==truth and replayed_trace==truth_trace,'replay_ms':replay_ms,'ingest_ms':ingest_ms,'task_bytes':len(truth),'trace_bytes':len(truth_trace)})
   other=next(j for j in range(n) if j!=i and (med/f'{j}.task').read_bytes()!=truth)
   rows.append({**base,'unit':i,'attack':'A1_substitution','accepted':(med/f'{other}.task').read_bytes()==replayed,'claimed_from':other})
   rows.append({**base,'unit':i,'attack':'A3_cached','accepted':truth==replayed,'note':'correct result; only one-use credit accounting can refuse it'})
   for cap in PARTIAL:
    part=folder/f'partial_{i}_{cap}';part.mkdir()
    begin=time.perf_counter();w.run(1,i,seed,n,cap,part,folder/'unused.pdbqt');ms=(time.perf_counter()-begin)*1000
    pool=(part/f'{i}.task').read_bytes();trace=(part/f'{i}.task.trace').read_bytes()
    evals=json.loads((part/f'{i}.task.json').read_text())['evals']
    rows.append({**base,'unit':i,'attack':'A2_partial','budget':cap,'attacker_ms':ms,'attacker_evals':evals,
                 'accepted_pool_only':pool==replayed,'accepted_pool_and_trace':pool==replayed and trace==replayed_trace})
  honest_final=final_score(job/'medium.pdbqt')
  k=pick_units(job,n)[0]
  for kind,values,fn in (('A8e_energy',ENERGY_DELTAS,tamper_energy),('A8c_shift',SHIFTS,tamper_shift)):
   for v in values:
    pool=folder/f'{kind}_{v}';shutil.copytree(med,pool,ignore=shutil.ignore_patterns('*.trace','*.json'))
    (pool/f'{k}.task').write_text(fn((med/f'{k}.task').read_text(),v))
    try:
     w.run(2,0,seed,n,CAP,pool,pool/'final.pdbqt');tampered=final_score(pool/'final.pdbqt')
     rows.append({**base,'unit':k,'attack':kind,'magnitude':v,'honest_final':honest_final,'tampered_final':tampered,
                  'final_changed':abs(tampered-honest_final)>1e-9,'pose_changed':digest(pool/'final.pdbqt')!=digest(job/'medium.pdbqt')})
    except Exception as e:rows.append({**base,'unit':k,'attack':kind,'magnitude':v,'error':str(e)})
 finally:w.close()
 return rows

def main():
 OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
 targets={t['target']:t for t in json.loads(INPUTS.read_text())['targets']}
 jobs=corpus_jobs()
 freeze(OUT/'phase1_manifest.json',{'protocol':digest(PROTOCOL),'runner':digest(Path(__file__)),
  'driver':digest(ROOT/'tmp/vina-published/vina_published_tasks_spacing0375.exe'),
  'corpus':sorted('/'.join(j.parts[-3:]) for j in jobs),'salt':SALT,'units_per_job':UNITS_PER_JOB,
  'partial_budgets':list(PARTIAL),'energy_deltas':list(ENERGY_DELTAS),'shifts_A':list(SHIFTS),'workers':WORKERS})
 path=OUT/'phase1.jsonl';done={r['id']+'/'+str(r['seed']) for r in read(path)}
 with ThreadPoolExecutor(max_workers=WORKERS) as pool:
  futures={pool.submit(job_eval,j,targets):j for j in jobs if j.parts[-2]+'/'+j.parts[-1] not in done}
  for f in as_completed(futures):
   j=futures[f]
   try:rows=f.result()
   except Exception as e:rows=[{'target':j.parts[-3],'id':j.parts[-2],'seed':int(j.parts[-1]),'attack':'job_error','error':str(e)}]
   for r in rows:append(path,r)
   print(j.parts[-3],j.parts[-2],j.parts[-1],len(rows),'rows',flush=True)
 print('PHASE1 COMPLETE',flush=True)

if __name__=='__main__':main()
