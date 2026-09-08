"""Pin inputs and predeclare the bounded-run grid before inspecting outcomes."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-runs';OLD=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
OUT.mkdir(parents=True,exist_ok=True)
records=json.loads((ROOT/'docs/evaluation/docking_lightweight_2026-09-07/ligands.json').read_text())['records']
maps=[]
for p in sorted((OLD/'maps').glob('fa10.*.map')):maps.append({'name':p.name,'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
ligands=[]
for r in records+[{'id':'crystal','label':'redocking'}]:
    p=OLD/'ligands'/(r['id']+'.pdbqt');ligands.append({**r,'path':p.relative_to(ROOT).as_posix(),'input_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
plan={'version':'whole-run-v1','scope':'Vina1.2.7, fixed PDBQT with flexible torsions, no_refine map objective. E1 unit uses direct positive31bit seed. Cap checked between MC steps.','maps':maps,'ligands':ligands,'caps':[1000,4000,16000],'runs':32,'seeds':[104729+i*13007 for i in range(32)],'browser_ligands':[r['id'] for r in records[:8]+records[16:24]],'browser_tiers':{'ligands':[1,4,16],'runs':[1,4,16]},'q':[1,2,4,8],'fractions':[.1,.25,.5,.75,.9,1.]}
payload=json.dumps(plan,indent=2)+'\n';(OUT/'plan.json').write_text(payload);print({'maps':len(maps),'map_bytes':sum(m['bytes'] for m in maps),'ligands':len(ligands)})
