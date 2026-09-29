"""Amendment 16: adaptive attacks on trace commitment, judged by exact replay.

Replays the phase-1 salted-hash sample (99 units over 33 corpus jobs) with the
control build and three attacker-built variants (scripts/
build_trace_attack_variants.py), comparing each pool and trace byte for byte
with the preserved honest output. The control must reproduce all 99 units
before variants are judged. R1 measures cross-unit recurrence of per-step
energies over every traced corpus job.
"""
import hashlib,json,sys,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_published_matched as rpm
from adversarial_replay_eval import corpus_jobs,pick_units,read,CAP
ROOT=rpm.ROOT
OUT=ROOT/'local-research/trace-attacks-2026-09-29'
WORK=ROOT/'tmp/trace-attacks/runs'
BUILD=ROOT/'tmp/trace-attacks/build_manifest.json'
INPUTS=ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json'
PROTOCOL_COMMIT='599cc0f'
VARIANTS=['control','v1_fastmath','v2_halflocal','v3_norefine']
WORKERS=4
START=threading.Lock()   # rpm.Worker reads the module-level EXE when it starts

def steps(trace):
 lines=trace.decode().split()
 return [(lines[i],lines[i+1]) for i in range(0,len(lines)-1,2)]

def first_diff(a,b):
 for k,(x,y) in enumerate(zip(a,b)):
  if x!=y:return k
 return None if len(a)==len(b) else min(len(a),len(b))

def job_eval(job,targets,exes):
 tname,lid,seed=job.parts[-3],job.parts[-2],int(job.parts[-1])
 t=targets[tname];l=next(x for x in t['ligands'] if x['id']==lid)
 med=job/'medium';n=len(list(med.glob('*.task')));rows=[]
 for name in VARIANTS:
  folder=WORK/name/tname/lid/str(seed);folder.mkdir(parents=True,exist_ok=True)
  with START:rpm.EXE=exes[name];w=rpm.Worker(t,l,folder)
  try:
   for i in pick_units(job,n):
    truth=(med/f'{i}.task').read_bytes();truth_trace=(med/f'{i}.task.trace').read_bytes()
    out=folder/f'unit_{i}';out.mkdir(exist_ok=True)
    b=time.perf_counter();w.run(1,i,seed,n,CAP,out,folder/'unused.pdbqt');ms=(time.perf_counter()-b)*1000
    pool=(out/f'{i}.task').read_bytes();trace=(out/f'{i}.task.trace').read_bytes()
    meta=json.loads((out/f'{i}.task.json').read_text())
    hs,vs=steps(truth_trace),steps(trace)
    rows.append({'target':tname,'id':lid,'seed':seed,'unit':i,'variant':name,'accepted':pool==truth and trace==truth_trace,
                 'pool_equal':pool==truth,'trace_equal':trace==truth_trace,'first_diff_step':first_diff(hs,vs),
                 'honest_steps':len(hs),'variant_steps':len(vs),'honest_evals':int(hs[-1][1]),'variant_evals':int(meta['evals']),
                 'wall_ms':ms})
  finally:w.close()
 return rows

def reuse(jobs):
 """R1: fraction of per-step energies in a unit bit-identical (as written) to
 one in another unit of the same job."""
 total=repeated=0;per_job=[]
 for job in jobs:
  units=[[s[0] for s in steps(p.read_bytes())] for p in sorted((job/'medium').glob('*.task.trace'))]
  counts={}
  for u in units:
   for e in set(u):counts[e]=counts.get(e,0)+1
  jt=sum(len(u) for u in units);jr=sum(sum(1 for e in u if counts[e]>1) for u in units)
  total+=jt;repeated+=jr;per_job.append({'job':'/'.join(job.parts[-3:]),'units':len(units),'steps':jt,'recurring':jr})
 return {'steps':total,'recurring':repeated,'fraction':repeated/total if total else None,'jobs':per_job}

def main():
 committed=__import__('subprocess').check_output(['git','show',PROTOCOL_COMMIT+':docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'],cwd=ROOT)
 assert committed.replace(b'\r\n',b'\n') in (ROOT/'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md').read_bytes().replace(b'\r\n',b'\n'),'Protocol not committed'
 build=json.loads(BUILD.read_text());exes={v:ROOT/build[v]['exe'] for v in VARIANTS}
 targets={t['target']:t for t in json.loads(INPUTS.read_text())['targets']}
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/'manifest.json').write_text(json.dumps({'amendment':16,'protocol_commit':PROTOCOL_COMMIT,'build':build,'budget':CAP,'workers':WORKERS,
  'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2))
 jobs=corpus_jobs();rows=[]
 with ThreadPoolExecutor(max_workers=WORKERS) as pool:
  futures=[pool.submit(job_eval,j,targets,exes) for j in jobs]
  for k,f in enumerate(as_completed(futures),1):
   rows+=f.result();print('jobs done',k,'/',len(jobs),flush=True)
 (OUT/'units.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
 r1=reuse(jobs);(OUT/'reuse.json').write_text(json.dumps(r1,indent=1))
 print('R1 recurring fraction',r1['fraction'])

if __name__=='__main__':main()
