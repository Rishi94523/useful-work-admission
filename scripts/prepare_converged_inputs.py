"""Post-hoc preparation audit; retain every original input and convergence flag."""
import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from rdkit.Chem import AllChem
from meeko import MoleculePreparation,PDBQTWriterLegacy
OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';dest=OUT/'converged_inputs.json'
if dest.exists():print('Preserved existing convergence audit');raise SystemExit(0)
rows=[]
for t in json.loads((OUT/'science_inputs.json').read_text())['targets']:
 if t.get('preparation_failed'):continue
 folder=ROOT/'tmp/adaptive-docking'/t['target']/'converged';folder.mkdir(exist_ok=True)
 for l in t['ligands']:
  p=ROOT/l['independent']['path'];m=Chem.SDMolSupplier(str(p.with_suffix('.sdf')),removeHs=False)[0];properties=AllChem.MMFFGetMoleculeProperties(m)
  row={'target':t['target'],'id':l['id'],'label':l['label'],'original_mmff_status':l.get('mmff_status'),'original_input_sha256':l['independent']['sha256']}
  if properties is None:row['error']='Missing MMFF parameters';rows.append(row);continue
  ff=AllChem.MMFFGetMoleculeForceField(m,properties);row['energy_before']=ff.CalcEnergy();started=time.perf_counter();statuses=[]
  for _ in range(5):
   statuses.append(ff.Minimize(maxIts=2000))
   if statuses[-1]==0:break
  row.update(statuses=statuses,converged=statuses[-1]==0,energy_after=ff.CalcEnergy(),relaxation_wall_ms=(time.perf_counter()-started)*1000)
  text,ok,error=PDBQTWriterLegacy.write_string(MoleculePreparation().prepare(m)[0])
  if not ok:row['error']=error;rows.append(row);continue
  out=folder/(l['id']+'.pdbqt');out.write_text(text,encoding='utf-8',newline='\n');w=Chem.SDWriter(str(out.with_suffix('.sdf')));w.write(m);w.close()
  row.update(path=out.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(out.read_bytes()).hexdigest());rows.append(row)
dest.write_text(json.dumps({'scope':'Post-hoc audit of the initially 200-step ETKDG/MMFF conformers. Up to five further 2000-step MMFF minimizations, stopping at convergence. Retains originals. Preparation ran during concurrent stock-quality controls, so wall times are not isolated economics. Initial diagnostic scope was three crystal ligands. A subsequent pre-outcome amendment extended docking and matched stock controls to all48 ranking inputs; see the frozen-plan chronology and converged_summary.json for outcomes.','rows':rows},indent=2)+'\n')
print('Converged',sum(r.get('converged',False) for r in rows),'of',len(rows),'inputs')
