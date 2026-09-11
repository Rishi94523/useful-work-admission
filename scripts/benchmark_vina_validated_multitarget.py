"""E32 versus many medium runs after an existing stock redocking gate.

Stock E4 source-crystal controls are checked before each expensive run; fresh E32
stock repeats are a separate experiment. This is redocking, not ranking evidence.
"""
import json,math,time
from pathlib import Path
from benchmark_vina_task_split import ROOT,BASE,OLD,start,call,stop,digest
from validate_vina_stock_controls import quality
OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10';OUT.mkdir(exist_ok=True)
reference=json.loads((ROOT/'docs/evaluation/vina_tasks_2026-09-10/split_equivalence.json').read_text())
dest=OUT/'medium_e32.json';rows=json.loads(dest.read_text()) if dest.exists() else []
for t in json.loads((OLD/'science_inputs.json').read_text())['targets']:
 if t.get('preparation_failed') or t['target']=='fa10' or any(r['target']==t['target'] for r in rows):continue
 ligand=ROOT/next(l for l in t['ligands'] if l['id']=='crystal')['source']['path'];stock=next(r for r in reference if r['target']==t['target'] and r['cap']==0)
 assert stock['input_sha256']==digest(ligand),'Historical gate input changed'
 gate=quality(ligand,ligand.with_suffix('.sdf'),stock['stock']['pose'])
 if not gate['redocking_gate']:rows.append({'target':t['target'],'gate':gate,'skipped':'Stock redocking failed'});continue
 folder=ROOT/'tmp/vina-validation'/('medium_'+t['target']);folder.mkdir(exist_ok=True);p=start(t,ligand)
 try:
  normal=call(p,0,0,32,0,folder/'normal',folder/'normal.pdbqt');nm=[json.loads((folder/'normal'/f'{i}.task.json').read_text()) for i in range(32)]
  budget=sum(m['evals'] for m in nm);cap=256000;n=math.ceil(budget/cap);assert n<=512
  medium=call(p,0,0,n,cap,folder/'medium',folder/'medium.pdbqt');mm=[json.loads((folder/'medium'/f'{i}.task.json').read_text()) for i in range(n)]
  normal_ms=sum(m['ms'] for m in nm);cumulative=[];total=0
  for m in mm:total+=m['ms'];cumulative.append(total)
  count=min(range(n),key=lambda i:abs(cumulative[i]-normal_ms))+1
  call(p,2,0,count,cap,folder/'medium',folder/'wall.pdbqt')
  old=BASE/'campaign'/t['target']/'crystal_source'/'normal_32.pdbqt'
  row={'target':t['target'],'gate_stock_E4':gate,'input_sha256':digest(ligand),'receptor_sha256':digest(ROOT/t['receptor']),'normal':normal,'normal_search_ms':normal_ms,'normal_evals':budget,'normal_quality':quality(ligand,ligand.with_suffix('.sdf'),(folder/'normal.pdbqt').read_text()),'normal_pose':(folder/'normal.pdbqt').read_text(),'historical_E32_pose_exact':old.read_bytes()==(folder/'normal.pdbqt').read_bytes(),'medium':medium,'medium_runs':n,'medium_search_ms':total,'medium_evals':sum(m['evals'] for m in mm),'medium_quality':quality(ligand,ligand.with_suffix('.sdf'),(folder/'medium.pdbqt').read_text()),'medium_pose':(folder/'medium.pdbqt').read_text(),'closest_time_runs':count,'closest_time_ratio':cumulative[count-1]/normal_ms,'closest_time_quality':quality(ligand,ligand.with_suffix('.sdf'),(folder/'wall.pdbqt').read_text()),'normal_units':nm,'medium_units':mm,'timing_scope':'Same sequential single-thread native worker. Other validation processes may be running; wall-time ratios are descriptive, not an isolated speedup claim.'}
  rows.append(row);dest.write_text(json.dumps(rows,indent=2)+'\n');print(t['target'],n,row['normal_quality']['top_rmsd_A'],row['medium_quality']['top_rmsd_A'],flush=True)
 finally:stop(p)
