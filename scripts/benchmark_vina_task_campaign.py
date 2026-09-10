"""Stock-shaped candidate pools: prefixes and matched-evaluation short-run arms."""
import json,math,time,hashlib
from pathlib import Path
from benchmark_vina_task_split import ROOT,OUT,BASE,OLD,start,call,stop
inputs=json.loads((OLD/'science_inputs.json').read_text())['targets'];corrected=json.loads((OLD/'converged_inputs.json').read_text())['rows'];dest=OUT/'campaign.jsonl'
done={r['key'] for r in map(json.loads,dest.read_text().splitlines())} if dest.exists() else set()
def save(row):
 with dest.open('a') as f:f.write(json.dumps(row)+'\n')
 done.add(row['key']);print(row['key'],round(row.get('search_ms',0)),flush=True)
for t in inputs:
 if t.get('preparation_failed'):continue
 ligands=[]
 for label in ['active','decoy']:
  ls=[l for l in t['ligands'] if l['label']==label]
  ligands += [(ls[i],'converged') for i in [0,2,5,7]]
 crystal=next(l for l in t['ligands'] if l['id']=='crystal');ligands += [(crystal,'source'),(crystal,'converged')]
 for l,conf in ligands:
  prefix=t['target']+':'+l['id']+':'+conf;folder=BASE/'campaign'/t['target']/(l['id']+'_'+conf);folder.mkdir(parents=True,exist_ok=True)
  source=l['source'] if conf=='source' else next(r for r in corrected if r['target']==t['target'] and r['id']==l['id'])
  ligand=ROOT/source['path'];maxruns=32 if l['id']=='crystal' else 8
  expected=[prefix+':normal:'+str(n) for n in [1,2,4,8]+([16,32] if maxruns==32 else [])]+[prefix+':matched:'+str(cap) for cap in [16000,64000,256000]]
  if all(k in done for k in expected):continue
  init=time.perf_counter();p=start(t,ligand);init_ms=(time.perf_counter()-init)*1000
  try:
   normal=folder/'normal';normal.mkdir(exist_ok=True)
   for i in range(maxruns):
    if not (normal/f'{i}.task.json').exists():call(p,1,i,maxruns,0,normal,folder/'unused.pdbqt')
    n=i+1
    if n not in [1,2,4,8,16,32] or prefix+':normal:'+str(n) in done:continue
    final=folder/f'normal_{n}.pdbqt';merged=call(p,2,0,n,0,normal,final);metrics=[json.loads((normal/f'{j}.task.json').read_text()) for j in range(n)]
    save({'key':prefix+':normal:'+str(n),'target':t['target'],'id':l['id'],'label':l['label'],'conformer':conf,'input_sha256':source['sha256'],'method':'normal','runs':n,'cap':0,'search_ms':sum(r['ms'] for r in metrics),'evals':sum(r['evals'] for r in metrics),'unit_metrics':metrics,'finalizer':merged,'init_ms':init_ms,'pose':final.read_text(),'task_bytes':sum((normal/f'{j}.task').stat().st_size for j in range(n)),'trace_bytes':sum((normal/f'{j}.task.trace').stat().st_size for j in range(n))})
   budget=json.loads((normal/'0.task.json').read_text())['evals']
   for cap in [16000,64000,256000]:
    key=prefix+':matched:'+str(cap)
    if key in done:continue
    n=math.ceil(budget/cap)
    if n>512:save({'key':key,'target':t['target'],'id':l['id'],'error':'budget requires over512 independent tasks','required_runs':n});continue
    tasks=folder/str(cap);final=folder/f'matched_{cap}.pdbqt'
    # Normal invocation materializes identical independent task boundaries; no
    # per-session wall claim is made for this cost/quality diagnostic.
    mono=call(p,0,0,n,cap,tasks,final);metrics=[json.loads((tasks/f'{i}.task.json').read_text()) for i in range(n)]
    save({'key':key,'target':t['target'],'id':l['id'],'label':l['label'],'conformer':conf,'input_sha256':source['sha256'],'method':'matched','runs':n,'cap':cap,'reference_evals':budget,'search_ms':sum(r['ms'] for r in metrics),'evals':sum(r['evals'] for r in metrics),'total_ms':mono['ms'],'score':mono['score'],'unit_metrics':metrics,'pose':final.read_text()})
  finally:stop(p)
