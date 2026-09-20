"""Stock-gated E32/256k comparison on frozen 22 A inputs, with parity gate."""
import hashlib,json,math,os,shutil,subprocess,threading,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from run_stock_diagnostic import metrics,auc

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'local-research/published-vina-validation-2026-09-15'
OUT=ROOT/'local-research/published-matched-2026-09-20'
WORK=ROOT/'tmp/vina-published/matched'
EXE=ROOT/'tmp/vina-published/vina_published_tasks.exe'

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));os.replace(tmp,p)
def freeze(p,x):
 if p.exists():assert json.loads(p.read_text())==x,'Immutable manifest changed: '+str(p)
 else:save(p,x)
def read(p):return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []
def append(p,x):
 with p.open('a') as f:f.write(json.dumps(x)+'\n');f.flush();os.fsync(f.fileno())

def build():
 compiler=shutil.which('g++');src=ROOT/'tmp/vina-tasks/source';driver=ROOT/'research/native/vina_published_worker.cpp';obj=EXE.with_suffix('.o')
 objects=sorted(p for p in (ROOT/'tmp/vina-tasks/build').glob('*.o') if p.name!='vina_task_worker.o')
 flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-I'+str(src),'-I'+str(ROOT/'tmp/docking-pilot/boost/ucrt64/include')]
 signature={'driver':digest(driver),'objects':{p.name:digest(p) for p in objects},'source':{p.name:digest(p) for p in src.iterdir() if p.is_file()},'flags':flags,'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]}
 manifest=OUT/'build.json'
 if manifest.exists():
  old=json.loads(manifest.read_text());assert old['inputs']==signature and digest(EXE)==old['exe_sha256'];return
 subprocess.run([compiler,*flags,'-c',str(driver),'-o',str(obj)],check=True)
 subprocess.run([compiler,str(obj),*map(str,objects),'-static-libgcc','-static-libstdc++','-o',str(EXE)],check=True)
 freeze(manifest,{'inputs':signature,'exe_sha256':digest(EXE)})

class Worker:
 def __init__(self,t,l,folder):
  assert digest(ROOT/t['receptor'])==t['receptor_sha256'] and digest(ROOT/l['path'])==l['sha256']
  # MinGW text-mode stream handling of the ADFR CRLF files failed at buffer
  # boundaries. Normalize line endings only in private execution copies.
  prepared=[]
  for name,source in [('receptor.pdbqt',ROOT/t['receptor']),('ligand.pdbqt',ROOT/l['path'])]:
   dest=folder/name;raw=source.read_bytes();normalized=raw.replace(b'\r\n',b'\n');assert raw.splitlines()==normalized.splitlines();dest.write_bytes(normalized);prepared.append(dest)
  self.error=(folder/'worker.stderr').open('w');self.p=subprocess.Popen([str(EXE),str(prepared[0]),'unused',str(prepared[1]),*map(str,t['center']),*map(str,t['size'])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.error,text=True)
  self.timer=threading.Timer(14400,self.p.kill);self.timer.daemon=True;self.timer.start()
  try:assert self.p.stdout.readline().strip()=='READY','Worker initialization failed'
  except BaseException:self.close();raise
 def run(self,mode,index,seed,n,cap,folder,pose):
  folder.mkdir(parents=True,exist_ok=True)
  self.p.stdin.write(f'{mode} {index} {seed} {n} {cap} 9 {folder.as_posix()} {pose.as_posix()}\n');self.p.stdin.flush()
  line=self.p.stdout.readline();assert line,'Worker stopped; inspect worker.stderr'
  return json.loads(line)
 def close(self):
  self.timer.cancel()
  if self.p.poll() is None:
   try:self.p.stdin.write('QUIT\n');self.p.stdin.flush();self.p.wait(timeout=10)
   except (OSError,subprocess.TimeoutExpired):self.p.kill();self.p.wait()
  self.error.close()

def pose_signature(path):
 # Official CLI retains poses within its default energy range; compare every
 # retained pose against the corresponding instrumented output, without fitting.
 result=[]
 for block in Path(path).read_text().split('ENDMDL'):
  atoms=[l for l in block.splitlines() if l.startswith(('ATOM','HETATM'))]
  if atoms:result.append([(l[12:16],l[77:].strip(),*[float(l[i:i+8]) for i in (30,38,46)]) for l in atoms])
 return result

def parity(t,stock):
 l=t['crystal'];seed=104729;folder=WORK/'parity_lf'/t['target'];folder.mkdir(parents=True,exist_ok=True);w=Worker(t,l,folder)
 try:
  normal=w.run(0,0,seed,32,0,folder/'normal',folder/'normal.pdbqt')
  ref=next(r for r in stock if r['target']==t['target'] and r['label']=='crystal' and r['seed']==seed)
  assert digest(ROOT/ref['pose_path'])==ref['pose_sha256']
  original=pose_signature(ROOT/ref['pose_path']);replica=pose_signature(folder/'normal.pdbqt')
  assert original and original==replica[:len(original)],'Official-stock pose mismatch'
  assert abs(normal['score']-ref['score'])<=.001,'Official-stock score mismatch'
  w.run(1,0,seed,32,0,folder/'replayed',folder/'unused.pdbqt')
  for suffix in ('task','task.trace'):assert digest(folder/'normal'/('0.'+suffix))==digest(folder/'replayed'/('0.'+suffix)),'Independent replay mismatch'
  w.run(2,0,seed,32,0,folder/'normal',folder/'refinalized.pdbqt')
  assert digest(folder/'normal.pdbqt')==digest(folder/'refinalized.pdbqt'),'Original finalizer mismatch'
  return {'target':t['target'],'ok':True,'official_retained_poses_exact':len(original),'pool_trace_exact':True,'finalizer_exact':True}
 finally:w.close()

def matched(t,l,seed):
 folder=WORK/t['target']/l['id']/str(seed);folder.mkdir(parents=True,exist_ok=True)
 record={'target':t['target'],'id':l['id'],'compound_id':l['compound_id'],'label':l['label'],'seed':seed,'input_sha256':l['sha256'],'ok':False};begin=time.perf_counter()
 try:
  w=Worker(t,l,folder)
  try:
   normal_path=folder/'normal_result.json'
   if normal_path.exists():
    normal=json.loads(normal_path.read_text());assert digest(folder/'normal.pdbqt')==normal['pose_sha256']
   else:
    result=w.run(0,0,seed,32,0,folder/'normal',folder/'normal.pdbqt')
    tasks=[json.loads((folder/'normal'/f'{i}.task.json').read_text()) for i in range(32)]
    normal={'score':result['score'],'evals':sum(x['evals'] for x in tasks),'search_ms':sum(x['ms'] for x in tasks),'total_ms':result['ms'],'pose_sha256':digest(folder/'normal.pdbqt')};save(normal_path,normal)
   n=math.ceil(normal['evals']/256000);assert 1<=n<=512,'Required medium unit count outside supported bound; no truncation'
   medium=w.run(0,0,seed,n,256000,folder/'medium',folder/'medium.pdbqt')
   tasks=[json.loads((folder/'medium'/f'{i}.task.json').read_text()) for i in range(n)]
   record.update(ok=True,normal=normal,medium={'score':medium['score'],'evals':sum(x['evals'] for x in tasks),'search_ms':sum(x['ms'] for x in tasks),'total_ms':medium['ms'],'pose_sha256':digest(folder/'medium.pdbqt'),'runs':n},folder=folder.relative_to(ROOT).as_posix())
  finally:w.close()
 except Exception as e:record['error']=str(e)
 record['wall_seconds']=time.perf_counter()-begin;return record

def analyze(rows,targets,seeds):
 results=[]
 for t in targets:
  per_seed=[];panels=[]
  for seed in seeds:
   compounds=[]
   for c in t['compounds']:
    states=[r for r in rows if r['target']==t['target'] and r['seed']==seed and r['compound_id']==c['id']]
    if len(states)!=c['states'] or not all(r['ok'] for r in states):continue
    compounds.append({'id':c['id'],'label':c['label'],'normal':min(r['normal']['score'] for r in states),'medium':min(r['medium']['score'] for r in states)})
   panels.append(compounds)
   m={method:metrics([{'ok':True,'score':r[method],'label':r['label']} for r in compounds],5000) for method in ('normal','medium')}
   per_seed.append({'seed':seed,'complete_compounds':len(compounds),**m})
  complete=all(len(p)==96 for p in panels);result={'target':t['target'],'complete':complete,'per_seed':per_seed}
  if complete:
   assert all([r['id'] for r in p]==[r['id'] for r in panels[0]] for p in panels)
   a=[i for i,r in enumerate(panels[0]) if r['label']=='active'];d=[i for i,r in enumerate(panels[0]) if r['label']=='decoy'];rng=np.random.default_rng(104729);deltas=[]
   for _ in range(5000):
    ai=rng.choice(a,len(a));di=rng.choice(d,len(d));deltas.append(np.mean([auc([p[i]['medium'] for i in ai],[p[i]['medium'] for i in di])-auc([p[i]['normal'] for i in ai],[p[i]['normal'] for i in di]) for p in panels]))
   ci=np.percentile(deltas,[2.5,97.5]).tolist();good=[r for r in rows if r['target']==t['target'] and r['ok']]
   result.update(mean_delta_auc=float(np.mean([s['medium']['auc']-s['normal']['auc'] for s in per_seed])),paired95=ci,noninferiority_demonstrated=ci[0]>-.05,evaluation_ratio=sum(r['medium']['evals'] for r in good)/sum(r['normal']['evals'] for r in good),search_time_ratio=sum(r['medium']['search_ms'] for r in good)/sum(r['normal']['search_ms'] for r in good))
  results.append(result)
 save(OUT/'comparison.json',results)

def main():
 OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
 cfg=json.loads((ROOT/'benchmarks/vina_published_validation.json').read_text());eligible=json.loads((BASE/'comparison_eligibility.json').read_text())
 assert digest(BASE/'inputs.json')==eligible['inputs_sha256'] and digest(BASE/'stock_gates.json')==eligible['stock_gates_sha256'] and digest(ROOT/'benchmarks/vina_published_validation.json')==eligible['protocol_sha256']
 targets=[t for t in json.loads((BASE/'inputs.json').read_text())['targets'] if t['target'] in eligible['eligible_targets']];seeds=cfg['comparison']['parent_seeds'];build()
 freeze(OUT/'execution_manifest_lf.json',{'protocol':eligible['protocol_sha256'],'inputs':eligible['inputs_sha256'],'eligibility':digest(BASE/'comparison_eligibility.json'),'build':digest(OUT/'build.json'),'runner':digest(Path(__file__)),'workers':8,'seeds':seeds,'input_transport':'CRLF to LF only, exact per-line bytes asserted; source files unchanged. Original failed CRLF parity attempt preserved.','scope':'Same input states/22A box, E32 versus ceil(E32 evaluations/256000) independent units; original merge/finalization; paired compound analysis.'})
 stock=read(BASE/'stock_jobs.jsonl');checks=read(OUT/'parity.jsonl');done={r['target'] for r in checks}
 save(OUT/'progress.json',{'phase':'parity','completed':len(checks),'total':len(targets)})
 with ThreadPoolExecutor(max_workers=5) as pool:
  for future in as_completed([pool.submit(parity,t,stock) for t in targets if t['target'] not in done]):
   try:r=future.result()
   except Exception as e:save(OUT/'parity_failure.json',{'error':str(e)});raise
   append(OUT/'parity.jsonl',r);checks.append(r);print('PARITY',r,flush=True)
 assert len(checks)==len(targets) and all(r['ok'] for r in checks)
 path=OUT/'matched.jsonl';rows=read(path);done={(r['target'],r['id'],r['seed']) for r in rows};assert len(done)==len(rows)
 # Interleave targets and preserve all seeds/states, regardless of outcomes.
 jobs=[(t,t['ligands'][i],seed) for seed in seeds for i in range(max(len(t['ligands']) for t in targets)) for t in targets if i<len(t['ligands'])];total=len(jobs)
 save(OUT/'progress.json',{'phase':'matched','completed':len(rows),'total':total,'workers':8})
 with ThreadPoolExecutor(max_workers=8) as pool:
  futures=[pool.submit(matched,t,l,s) for t,l,s in jobs if (t['target'],l['id'],s) not in done]
  for future in as_completed(futures):
   r=future.result();append(path,r);rows.append(r);save(OUT/'progress.json',{'phase':'matched','completed':len(rows),'total':total,'failures':sum(not r['ok'] for r in rows),'updated':time.time(),'workers':8});print(r['target'],r['id'],r['seed'],r['ok'],flush=True)
 analyze(rows,targets,seeds);save(OUT/'progress.json',{'phase':'complete','completed':len(rows),'total':total,'failures':sum(not r['ok'] for r in rows)})

if __name__=='__main__':main()
