"""Validate the immutable selected chemistry and runtime hashes; local evidence."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);args=p.parse_args();protocol=json.loads(Path(args.protocol).read_text());out=ROOT/protocol['output_directory']
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
inputs=json.loads((out/'large_inputs.json').read_text());rows=[]
assert [t['target'] for t in inputs['targets']]==protocol['targets']
for target in inputs['targets']:
 assert digest(ROOT/target['receptor'])==target['receptor_sha256']
 assert digest(out/(target['target']+'_selection.json'))==target['selection_sha256']
 for ligand in target['ligands']:
  path=ROOT/ligand['path'];assert digest(path)==ligand['sha256']
  m=next(iter(Chem.SDMolSupplier(str(path.with_suffix('.sdf')),removeHs=False)))
  assert m is not None and Chem.MolToSmiles(Chem.RemoveHs(m))==ligand['smiles']
  assert np.isfinite(m.GetConformer().GetPositions()).all()
  coordinates=[[float(line[i:i+8]) for i in [30,38,46]] for line in path.read_text().splitlines() if line.startswith(('ATOM','HETATM'))]
  assert coordinates and np.isfinite(coordinates).all()
 rows.append({'target':target['target'],'validated':len(target['ligands']),'preparation_failures':target['failures'],'active_count':sum(l['label']=='active' for l in target['ligands']),'decoy_count':sum(l['label']=='decoy' for l in target['ligands'])})
runtime={str(p.relative_to(ROOT)):digest(p) for p in [ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe',ROOT/'tmp/vina-tasks/vina_tasks.exe']}
r={'rows':rows,'protocol_sha256':digest(Path(args.protocol)),'inputs_sha256':digest(out/'large_inputs.json'),'runtime_sha256':runtime,'scope':'Selected source SMILES matches prepared SDF graph; finite SDF/PDBQT coordinates, receptor and ligand hashes. Does not establish biochemical suitability of protonation/cofactors.'}
(out/'input_validation.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
