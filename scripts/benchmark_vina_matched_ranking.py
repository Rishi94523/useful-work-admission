"""Matched-E8 medium-run ranking on the previously fixed4+4 subset.

Exploratory comparison only. Full8+8 stock panels were analyzed first. HS90A is
not retuned or erased: its failed stock gate remains in the report.
"""
import hashlib,json,math
from concurrent.futures import ThreadPoolExecutor,as_completed
from benchmark_vina_task_split import ROOT,BASE,OLD,start,call,stop
OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10';dest=OUT/'matched_ranking.json'
targets=json.loads((OLD/'science_inputs.json').read_text())['targets'];prepared=json.loads((OLD/'converged_inputs.json').read_text())['rows']
controls=[json.loads(x) for x in (ROOT/'docs/evaluation/vina_tasks_2026-09-10/campaign.jsonl').read_text().splitlines()]
tasks=[r for r in controls if r['target'] in ['fa10','tryb1'] and r['id']!='crystal' and r['method']=='normal' and r['runs']==8]
rows=json.loads(dest.read_text()) if dest.exists() else [];done={(r['target'],r['id']) for r in rows}
def run(reference):
 t=next(t for t in targets if t['target']==reference['target']);spec=next(s for s in prepared if s['target']==t['target'] and s['id']==reference['id']);ligand=ROOT/spec['path'];assert hashlib.sha256(ligand.read_bytes()).hexdigest()==reference['input_sha256']==spec['sha256']
 folder=ROOT/'tmp/vina-validation/ranking'/t['target']/reference['id'];folder.mkdir(parents=True,exist_ok=True);p=start(t,ligand)
 try:
  cap=256000;n=math.ceil(reference['evals']/cap);assert n<=512
  result=call(p,0,0,n,cap,folder/'units',folder/'final.pdbqt');metrics=[json.loads((folder/'units'/f'{i}.task.json').read_text()) for i in range(n)]
  return {'target':t['target'],'id':reference['id'],'label':reference['label'],'input_sha256':spec['sha256'],'medium_runs':n,'medium_evals':sum(m['evals'] for m in metrics),'reference_evals':reference['evals'],'medium_search_ms':sum(m['ms'] for m in metrics),'reference_search_ms':reference['search_ms'],'medium_score':result['score'],'normal_score':reference['finalizer']['score'],'pose':(folder/'final.pdbqt').read_text(),'unit_metrics':metrics,'scope':'New medium measurements matched to historical normal E8 evaluation counts on exactly rehashed inputs. Two concurrent workers; not a wall-speedup comparison. Fixed earlier4+4 subset; not an independent large ranking benchmark.'}
 finally:stop(p)
with ThreadPoolExecutor(max_workers=2) as pool:
 futures=[pool.submit(run,r) for r in tasks if (r['target'],r['id']) not in done]
 for future in as_completed(futures):
  r=future.result();rows.append(r);dest.write_text(json.dumps(rows,indent=2)+'\n');print(r['target'],r['id'],r['medium_runs'],r['medium_score'],flush=True)
