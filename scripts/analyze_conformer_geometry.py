"""Diagnostic lower bound from independently movable rigid PDBQT fragments.

This relaxes torsion-tree constraints. When all graph automorphisms are enumerated,
the bound cannot exceed any achievable rigid-fragment docking RMSD. It diagnoses
conformer limitations; it does not validate molecular strain or binding affinity.
"""
import json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
def error(a,b):
 a=a-a.mean(axis=0);b=b-b.mean(axis=0);u,_,vt=np.linalg.svd(a.T@b);fix=np.eye(3);fix[-1,-1]=np.linalg.det(u@vt);return float(((a@u@fix@vt-b)**2).sum())
sanity=np.array([[0.,0,0],[1,0,0],[0,2,0],[0,0,3]])
assert error(sanity,sanity@np.array([[0.,-1,0],[1,0,0],[0,0,1]])+5)<1e-20
assert error(sanity,sanity*np.array([-1,1,1]))>.01  # reflection must not be a rotation
results=[]
for target in json.loads((OUT/'science_inputs.json').read_text())['targets']:
 if target.get('preparation_failed'):continue
 l=next(l for l in target['ligands'] if l['id']=='crystal');ip=ROOT/l['independent']['path'];rp=ROOT/l['source']['path']
 probe=Chem.RemoveHs(Chem.SDMolSupplier(str(ip.with_suffix('.sdf')))[0]);ref=Chem.RemoveHs(Chem.SDMolSupplier(str(rp.with_suffix('.sdf')))[0])
 a=np.array(probe.GetConformer().GetPositions());b=np.array(ref.GetConformer().GetPositions());lines=ip.read_text().splitlines();atoms=[x for x in lines if x.startswith(('ATOM','HETATM')) and x[77:].strip() not in ['H','HD','G0','G1','G2','G3']]
 xyz=np.array([[float(x[k:k+8]) for k in [30,38,46]] for x in atoms]);_,order=linear_sum_assignment(np.linalg.norm(a[:,None,:]-xyz[None,:,:],axis=-1));assert np.linalg.norm(a-xyz[order],axis=1).max()<.01
 serial_to_atom={int(atoms[j][6:11]):i for i,j in enumerate(order)};rotors=set()
 for line in lines:
  if line.startswith('BRANCH '):
   _,i,j=line.split();rotors.add(tuple(sorted([serial_to_atom[int(i)],serial_to_atom[int(j)]])))
 adjacency={i:set() for i in range(len(a))}
 for bond in probe.GetBonds():
  i,j=bond.GetBeginAtomIdx(),bond.GetEndAtomIdx()
  if tuple(sorted([i,j])) not in rotors:adjacency[i].add(j);adjacency[j].add(i)
 fragments=[];remaining=set(adjacency)
 while remaining:
  todo=[remaining.pop()];component=[]
  while todo:
   i=todo.pop();component.append(i)
   for j in adjacency[i]&remaining:remaining.remove(j);todo.append(j)
  fragments.append(sorted(component))
 mappings=ref.GetSubstructMatches(probe,uniquify=False,useChirality=False,maxMatches=10000);assert mappings
 values=[sum(error(a[f],b[np.asarray(mapping)[f]]) for f in fragments) for mapping in mappings];best=int(np.argmin(values));mapping=np.asarray(mappings[best]);per=[{'atoms':f,'rmsd_A':float(np.sqrt(error(a[f],b[mapping[f]])/len(f)))} for f in fragments]
 results.append({'target':target['target'],'heavy_atoms':len(a),'rotatable_pdbqt_edges':len(rotors),'rigid_fragments':len(fragments),'automorphisms':len(mappings),'enumeration_exhaustive':len(mappings)<10000,'relaxed_rigid_fragment_rmsd_A':float(np.sqrt(min(values)/len(a))),'fragments_at_best_mapping':per})
out={'scope':'Independent versus crystal conformer, same molecular graph. Each PDBQT rigid fragment may rotate/translate independently, relaxing docking constraints; all returned full-graph atom mappings considered. Values are a lower bound only when mapping enumeration is exhaustive. Does not diagnose scoring errors or certify feasible attainment of the bound.','targets':results}
(OUT/'conformer_geometry.json').write_text(json.dumps(out,indent=2)+'\n');print([{k:r[k] for k in ['target','automorphisms','relaxed_rigid_fragment_rmsd_A']} for r in results])
