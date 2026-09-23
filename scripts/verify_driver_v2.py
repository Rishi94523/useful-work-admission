"""Verify the v2 rescoring driver against amendment 8 before it becomes the
deployment candidate.

A. G1 and G2 on v2: the v2 instrumented reference CLI and the v2 driver must be
   coordinate-identical to the same unpatched reference (R1) used for v1, and
   v2 single-unit replay and re-finalization must be byte-exact.
B. Honest pools: v1 and v2 finalize every corpus pool; outputs must be
   byte-identical. Finalization is timed for both to measure rescoring overhead.
C. The phase-6 attacks are repeated on v2 with the unchanged harness, and the
   falsified-energy deltas propagated onto the campaign as before.

v1 is only read, never modified. Each part writes its own rows.
"""
import hashlib,json,os,shutil,statistics,subprocess,sys,threading,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import run_published_matched as R
import scientific_integrity_eval as S
from verify_build_equivalence import normalize,poses,dock
from adversarial_replay_eval import corpus_jobs

OUT=ROOT/'local-research/driver-v2-2026-09-23'
WORK=ROOT/'tmp/driver-v2-verify'
V1=ROOT/'tmp/vina-published/vina_published_tasks_spacing0375.exe'
V2=ROOT/'tmp/vina-published/vina_published_tasks_v2.exe'
R2V2=ROOT/'tmp/vina-reference/vina_ref_instrumented_v2.exe'
REF=ROOT/'tmp/vina-reference/work'
INPUTS=ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json'
ELIGIBLE=ROOT/'local-research/published-vina-validation-2026-09-15/comparison_eligibility.json'
SEED=104729
TIMING_REPEATS=3

class Driver:
 """The frozen driver protocol, with the executable chosen explicitly."""
 def __init__(self,exe,t,l,folder):
  folder.mkdir(parents=True,exist_ok=True);prepared=[]
  for name,source in (('receptor.pdbqt',ROOT/t['receptor']),('ligand.pdbqt',ROOT/l['path'])):
   dest=folder/name;raw=source.read_bytes();lf=raw.replace(b'\r\n',b'\n');assert raw.splitlines()==lf.splitlines();dest.write_bytes(lf);prepared.append(dest)
  self.err=(folder/'driver.stderr').open('w')
  self.p=subprocess.Popen([str(exe),str(prepared[0]),'unused',str(prepared[1]),*map(str,t['center']),*map(str,t['size'])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,text=True)
  assert self.p.stdout.readline().strip()=='READY','Driver initialization failed'
 def run(self,mode,index,seed,n,cap,folder,pose):
  folder.mkdir(parents=True,exist_ok=True)
  self.p.stdin.write(f'{mode} {index} {seed} {n} {cap} 9 {folder.as_posix()} {pose.as_posix()}\n');self.p.stdin.flush()
  line=self.p.stdout.readline();assert line,'Driver stopped';return json.loads(line)
 def close(self):
  if self.p.poll() is None:
   try:self.p.stdin.write('QUIT\n');self.p.stdin.flush();self.p.wait(timeout=10)
   except Exception:self.p.kill()
  self.err.close()

def gates(t):
 """G1 and G2 for one crystal target on v2."""
 name=t['target'];folder=WORK/'gates'/name;shutil.rmtree(folder,ignore_errors=True);folder.mkdir(parents=True)
 ref=poses(REF/name/'r1_stock/out.pdbqt')
 inputs=folder/'inputs';inputs.mkdir()
 rec=normalize(ROOT/t['receptor'],inputs/'receptor.pdbqt');lig=normalize(ROOT/t['crystal']['path'],inputs/'ligand.pdbqt')
 args=['--receptor',str(rec),'--ligand',str(lig),'--cpu','1','--seed',str(SEED),'--exhaustiveness','32','--num_modes','9']
 for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['center'][i]),'--size_'+x,str(t['size'][i])]
 r2=dock(R2V2,name,folder/'r2_v2',args,split=folder/'r2_v2_split')
 r2p=poses(r2['pose_path'])
 d=Driver(V2,t,t['crystal'],folder/'driver')
 try:
  d.run(0,0,SEED,32,0,folder/'normal',folder/'normal.pdbqt');dp=poses(folder/'normal.pdbqt')
  d.run(1,0,SEED,32,0,folder/'replay',folder/'unused.pdbqt')
  replay=all(R.digest(folder/'normal'/('0.'+s))==R.digest(folder/'replay'/('0.'+s)) for s in ('task','task.trace'))
  d.run(2,0,SEED,32,0,folder/'normal',folder/'refinal.pdbqt')
  refinal=R.digest(folder/'normal.pdbqt')==R.digest(folder/'refinal.pdbqt')
 finally:d.close()
 same=lambda a,b:bool(a) and a==b[:len(a)]
 return {'target':name,'g1_instrumentation_identical':same(ref,r2p) and len(ref)==len(r2p),'g2_driver_identical':same(ref,dp),
         'replay_exact':replay,'refinalize_exact':refinal,'reference_poses':len(ref)}

def honest_and_timing(job,targets):
 """Finalize the untouched pool with v1 and v2, alternating, timing each."""
 tname,lid,seed=job.parts[-3],job.parts[-2],int(job.parts[-1]);t=targets[tname];l=next(x for x in t['ligands'] if x['id']==lid)
 n=len(list((job/'medium').glob('*.task')));folder=WORK/'honest'/tname/lid/str(seed);shutil.rmtree(folder,ignore_errors=True)
 pool=folder/'pool';shutil.copytree(job/'medium',pool,ignore=shutil.ignore_patterns('*.trace','*.json'))
 drivers={'v1':Driver(V1,t,l,folder/'v1'),'v2':Driver(V2,t,l,folder/'v2')};times={'v1':[],'v2':[]};outs={}
 try:
  for rep in range(TIMING_REPEATS):
   for v in (('v1','v2') if rep%2==0 else ('v2','v1')):
    pose=folder/f'{v}_{rep}.pdbqt';begin=time.perf_counter();drivers[v].run(2,0,seed,n,S.CAP,pool,pose);times[v].append((time.perf_counter()-begin)*1000);outs.setdefault(v,R.digest(pose))
 finally:
  for d in drivers.values():d.close()
 shutil.rmtree(folder,ignore_errors=True)
 m1,m2=statistics.median(times['v1']),statistics.median(times['v2'])
 return {'target':tname,'id':lid,'seed':seed,'units':n,'identical':outs['v1']==outs['v2'],'campaign_match':outs['v1']==R.digest(job/'medium.pdbqt'),
         'v1_finalize_ms':m1,'v2_finalize_ms':m2,'rescore_overhead_ms':m2-m1,'client_work_ms':n*1520}

def main():
 OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
 manifest={'protocol':R.digest(S.PROTOCOL),'runner':R.digest(Path(__file__)),'v1_driver':R.digest(V1),'v2_driver':R.digest(V2),'v2_reference':R.digest(R2V2),
  'v2_build':R.digest(ROOT/'tmp/vina-tasks-v2/build_manifest.json'),'reference_outputs':{p.parent.parent.name:R.digest(p) for p in sorted(REF.glob('*/r1_stock/out.pdbqt'))}}
 mp=OUT/'manifest.json'
 if mp.exists():assert json.loads(mp.read_text())==manifest,'Immutable manifest changed'
 else:mp.write_text(json.dumps(manifest,indent=2))
 data=json.loads(INPUTS.read_text());eligible=json.loads(ELIGIBLE.read_text())['eligible_targets']
 targets={t['target']:t for t in data['targets']};jobs=corpus_jobs()
 with ThreadPoolExecutor(max_workers=12) as pool:
  gate_futures=[pool.submit(gates,targets[n]) for n in eligible]
  honest_futures=[pool.submit(honest_and_timing,j,targets) for j in jobs]
  honest=[f.result() for f in honest_futures];print('B honest+timing done',flush=True)
  (OUT/'honest_and_timing.json').write_text(json.dumps(honest,indent=2))
  # C: the unchanged phase-6 harness, pointed at v2. All workers in this part use v2.
  R.EXE=V2;S.WORK=WORK/'attacks'
  attacks=[r for rows in pool.map(lambda j:S.job_eval(j,targets),jobs) for r in rows];print('C attacks done',flush=True)
  (OUT/'attacks.jsonl').write_text(''.join(json.dumps(r)+chr(10) for r in attacks))
  g=[f.result() for f in gate_futures];print('A gates done',flush=True)
 (OUT/'gates.json').write_text(json.dumps(g,indent=2))
 relabelled=[dict(r,experiment='I-b_duplicate') for r in attacks if r['experiment']=='I-c_duplicate_fake_energy']
 (OUT/'propagation_fake_energy.json').write_text(json.dumps(S.propagate(relabelled),indent=2))
 (OUT/'propagation_duplicate.json').write_text(json.dumps(S.propagate([r for r in attacks if r['experiment']=='I-b_duplicate']),indent=2))
 print('V2 VERIFICATION COMPLETE',flush=True)

if __name__=='__main__':main()
