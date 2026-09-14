"""Report chemical states and invariants without inspecting ranking outcomes."""
import collections,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem,rdBase
def atoms(path):
 return [{'residue':l[17:27].strip(),'name':l[12:16].strip(),'type':l[77:].strip(),'charge':float(l[70:76]),'xyz':np.array([float(l[i:i+8]) for i in [30,38,46]])} for l in path.read_text().splitlines() if l.startswith(('ATOM','HETATM'))]
def main():
 cfg=json.loads((ROOT/'benchmarks/vina_stock_diagnostic.json').read_text());out=ROOT/cfg['output_directory'];inputs=json.loads((out/'inputs.json').read_text());reports=[]
 for t in inputs['targets']:
  selected=json.loads((out/(t['target']+'_split.json')).read_text());dev={l['parent'] for l in selected['development']};held={l['parent'] for l in selected['heldout']};assert not dev&held
  crystal=Chem.RemoveHs(Chem.SDMolSupplier(str((ROOT/t['crystal']['path']).with_suffix('.sdf')))[0]);xyz=crystal.GetConformer().GetPositions();receptors={};atom_sets={}
  for variant,path in t['receptors'].items():
   p=ROOT/path;assert hashlib.sha256(p.read_bytes()).hexdigest()==t['receptor_hashes'][variant];a=atoms(p);heavy=[x for x in a if x['type'] not in ['H','HD']];near=[x for x in a if np.linalg.norm(x['xyz']-xyz,axis=1).min()<=6]
   atom_sets[variant]=heavy
   receptors[variant]={'atoms':len(a),'heavy_atoms':len(heavy),'types':dict(collections.Counter(x['type'] for x in a)),'partial_charge_sum':sum(x['charge'] for x in a),'within_6A_types':dict(collections.Counter(x['type'] for x in near)),'within_6A_residues':sorted({x['residue'] for x in near})}
  old=atom_sets['legacy'];new=atom_sets['source_state'];dist=np.linalg.norm(np.array([a['xyz'] for a in old])[:,None]-np.array([a['xyz'] for a in new])[None],axis=-1);coordinate_change=max(float(dist.min(0).max()),float(dist.min(1).max()));assert len(old)==len(new) and coordinate_change<=.02
  type_changes=[{'residue':a['residue'],'atom':a['name'],'legacy':a['type'],'source_state':new[j]['type'],'min_crystal_distance_A':float(np.linalg.norm(a['xyz']-xyz,axis=1).min())} for a,j in zip(old,dist.argmin(1)) if a['type']!=new[j]['type']]
  ligand_states={}
  for split,ligands in t['splits'].items():
   torsions=[];charges=collections.Counter();box_oversize=collections.Counter()
   for l in ligands:
    p=ROOT/l['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==l['sha256'];m=Chem.SDMolSupplier(str(p.with_suffix('.sdf')),removeHs=False)[0];assert Chem.MolToSmiles(Chem.RemoveHs(m))==l['smiles'];assert np.isfinite(m.GetConformer().GetPositions()).all();charges[str(Chem.GetFormalCharge(m))]+=1
    torsions.append(int(next(s.split()[1] for s in p.read_text().splitlines() if s.startswith('TORSDOF'))))
    span=np.ptp(Chem.RemoveHs(m).GetConformer().GetPositions(),axis=0)
    for key,box in t['boxes'].items():box_oversize[key]+=int(any(span>box['size']))
   ligand_states[split]={'count':len(ligands),'formal_charge_counts':dict(charges),'torsdof_min_median_max':[min(torsions),float(np.median(torsions)),max(torsions)],'supplied_axis_span_exceeds_box':dict(box_oversize)}
  reports.append({'target':t['target'],'parent_overlap':len(dev&held),'receptors':receptors,'legacy_to_revised_max_heavy_coordinate_change_A':coordinate_change,'heavy_atom_type_changes':type_changes,'ligand_states':ligand_states,'note':'Axis span is an input diagnostic, not an orientation-invariant fit test. No molecular states or boxes changed by this audit.'})
 (out/'chemical_state_audit.json').write_text(json.dumps({'rdkit_version':rdBase.rdkitVersion,'targets':reports},indent=2)+'\n');print(json.dumps(reports,indent=2))
if __name__=='__main__':main()
