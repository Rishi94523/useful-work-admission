"""Resume-safe stock gate followed by matched computations on passing targets."""
import hashlib,json,math,re,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from benchmark_vina_task_split import ROOT,BASE,call,stop
OUT=ROOT/'docs/evaluation/vina_followup_2026-09-12';targets=json.loads((OUT/'large_inputs.json').read_text())['targets'];path=OUT/'large_stock.jsonl'
def read(p):return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
def append(p,row):
 with p.open('a') as f:f.write(json.dumps(row)+'\n');f.flush()
 print(row['target'],row['id'],row.get('seed'),row.get('score',row.get('medium_score')),flush=True)
def stock(t,l):
 ligand=ROOT/l['path'];assert hashlib.sha256(ligand.read_bytes()).hexdigest()==l['sha256'];folder=ROOT/'tmp/vina-followup/stock'/t['target'];folder.mkdir(parents=True,exist_ok=True);dest=folder/(l['id']+'.pdbqt')
 args=[str(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'--receptor',str(ROOT/t['receptor']),'--ligand',str(ligand),'--cpu','1','--seed','104729','--exhaustiveness','8','--num_modes','9','--out',str(dest)]
 for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['center'][i]),'--size_'+x,'30']
 row={'target':t['target'],'id':l['id'],'label':l['label'],'seed':104729,'input_sha256':l['sha256']};start=time.perf_counter()
 try:
  r=subprocess.run(args,capture_output=True,text=True,timeout=900);row.update(ok=r.returncode==0,returncode=r.returncode,stderr=r.stderr)
  if r.returncode==0:row.update(score=float(re.search(r'REMARK VINA RESULT:\s+([-\d.]+)',dest.read_text()).group(1)),pose=dest.read_text())
 except subprocess.TimeoutExpired:row.update(ok=False,error='900 second stock timeout')
 row['wall_ms']=1000*(time.perf_counter()-start);return row
existing=read(path);done={(r['target'],r['id']) for r in existing}
with ThreadPoolExecutor(max_workers=4) as pool:
 futures=[pool.submit(stock,t,l) for t in targets for l in t['ligands'] if (t['target'],l['id']) not in done]
 for f in as_completed(futures):r=f.result();append(path,r);existing.append(r)
gates=[]
for t in targets:
 rs=[r for r in existing if r['target']==t['target']];valid=[r for r in rs if r['ok']];a=np.array([r['score'] for r in valid if r['label']=='active']);d=np.array([r['score'] for r in valid if r['label']=='decoy']);complete=len(valid)==96 and not t['failures']
 def auc(a,d):return float(((a[:,None]<d)+.5*(a[:,None]==d)).mean())
 point=auc(a,d) if len(a) and len(d) else None;ci=None;ef=None
 if complete:
  rng=np.random.default_rng(104729);ci=np.percentile([auc(rng.choice(a,len(a)),rng.choice(d,len(d))) for _ in range(5000)],[2.5,97.5]).tolist();k=math.ceil(.1*len(rs));ef=sum(r['label']=='active' for r in sorted(valid,key=lambda x:x['score'])[:k])/k/(32/96)
 passed=bool(complete and point>=.75 and ci[0]>.60 and ef>=1.5);gates.append({'target':t['target'],'complete':complete,'auc':point,'bootstrap95':ci,'ef10':ef,'passed':passed,'failed_ids':[r['id'] for r in rs if not r['ok']]})
(OUT/'large_stock_gates.json').write_text(json.dumps(gates,indent=2)+'\n');print('GATES',gates,flush=True)
dest=OUT/'large_matched.jsonl';done={(r['target'],r['id'],r['seed']) for r in read(dest)}
def matched(t,l,seed):
 folder=ROOT/'tmp/vina-followup/matched'/t['target']/l['id']/str(seed);folder.mkdir(parents=True,exist_ok=True)
 p=subprocess.Popen([str(BASE/'vina_tasks.exe'),str(ROOT/t['receptor']),'unused',str(ROOT/l['path']),*map(str,t['center'])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if p.stdout.readline().strip()!='READY':raise RuntimeError(p.stderr.read())
 def run(mode,n,cap,name):
  directory=folder/name;directory.mkdir(exist_ok=True);pose=folder/(name+'.pdbqt');p.stdin.write(f'{mode} 0 {seed} {n} {cap} 9 {directory.as_posix()} {pose.as_posix()}\n');p.stdin.flush();line=p.stdout.readline()
  if not line:raise RuntimeError(p.stderr.read())
  return json.loads(line),[json.loads((directory/f'{i}.task.json').read_text()) for i in range(n)],pose
 try:
  normal,nm,npth=run(0,8,0,'normal');budget=sum(m['evals'] for m in nm);n=math.ceil(budget/256000)
  if n>512:raise RuntimeError('Over512 tasks')
  medium,mm,mpth=run(0,n,256000,'medium')
  return {'target':t['target'],'id':l['id'],'label':l['label'],'seed':seed,'input_sha256':l['sha256'],'normal_score':normal['score'],'medium_score':medium['score'],'normal_evals':budget,'medium_evals':sum(m['evals'] for m in mm),'normal_ms':sum(m['ms'] for m in nm),'medium_ms':sum(m['ms'] for m in mm),'medium_runs':n,'normal_pose':npth.read_text(),'medium_pose':mpth.read_text()}
 finally:stop(p)
with ThreadPoolExecutor(max_workers=4) as pool:
 futures=[pool.submit(matched,t,l,seed) for t in targets if next(g['passed'] for g in gates if g['target']==t['target']) for l in t['ligands'] for seed in [104729,130363,155921] if (t['target'],l['id'],seed) not in done]
 for f in as_completed(futures):append(dest,f.result())
print('Completed gated campaign',flush=True)
