"""Demonstrate why deferred scientific pools must not imply validated coverage."""
import json,shutil,time
from pathlib import Path
from benchmark_vina_task_split import ROOT,BASE,OLD,start,call,stop
from validate_vina_stock_controls import quality
OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10';t=next(t for t in json.loads((OLD/'science_inputs.json').read_text())['targets'] if t['target']=='tryb1')
ligand=ROOT/next(l for l in t['ligands'] if l['id']=='crystal')['source']['path'];source=BASE/'campaign/tryb1/crystal_source';folder=ROOT/'tmp/vina-validation/poisoning';folder.mkdir(exist_ok=True)
p=start(t,ligand);rows=[]
try:
 for attack in ['honest','one_fake_low_energy','all_same_cheap_output']:
  dest=folder/attack;dest.mkdir(exist_ok=True)
  for i in range(32):shutil.copyfile(source/'normal'/f'{i}.task',dest/f'{i}.task')
  cheap=(source/'16000/0.task').read_text()
  if attack=='one_fake_low_energy':
   lines=cheap.splitlines();lines=[lines[0]]+['-1000 '+line.split(' ',1)[1] for line in lines[1:] if line.strip()];(dest/'0.task').write_text('\n'.join(lines)+'\n')
  elif attack=='all_same_cheap_output':
   for i in range(32):(dest/f'{i}.task').write_text(cheap)
  merged=call(p,2,0,32,0,dest,dest/'final.pdbqt');changed=[i for i in range(32) if (dest/f'{i}.task').read_bytes()!=(source/'normal'/f'{i}.task').read_bytes()]
  # Full-run replay uses the existing authoritative relation. This check is an
  # actual molecular replay for the first altered unit, not score-only checking.
  replay=None
  if changed:
   i=changed[0];before=time.perf_counter();call(p,1,i,32,0,dest/'replay',dest/'unused.pdbqt');replay={'unit':i,'ms':1000*(time.perf_counter()-before),'exact':(dest/'replay'/f'{i}.task').read_bytes()==(dest/f'{i}.task').read_bytes()};assert not replay['exact']
  row={'attack':attack,'changed_units':changed,'merged':merged,'quality':quality(ligand,ligand.with_suffix('.sdf'),(dest/'final.pdbqt').read_text()),'selected_whole_run_replay':replay,'q1_miss_probability':(32-len(changed))/32,'pose':(dest/'final.pdbqt').read_text()};rows.append(row)
 (OUT/'provisional_poisoning.json').write_text(json.dumps({'scope':'Actual original native merger/finalizer, one source-crystal target,32unit pool. Malicious outputs are fabricated from one existing16k run. This tests scientific contamination separately from the unchanged whole-run verification relation; no deployed deferred policy.','rows':rows},indent=2)+'\n');print([(r['attack'],r['quality']['top_rmsd_A']) for r in rows])
finally:stop(p)
