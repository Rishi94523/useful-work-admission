"""Independent checks of the frozen selected-input manifest, without docking."""
import hashlib, json, platform, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem, rdBase
import meeko
BASE=ROOT/'docs/evaluation/vina_followup_2026-09-12'
manifest=json.loads((BASE/'large_inputs.json').read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
targets=[]
for t in manifest['targets']:
    selection=json.loads((BASE/(t['target']+'_selection.json')).read_text())
    assert sha(BASE/(t['target']+'_selection.json'))==t['selection_sha256']
    assert sha(ROOT/t['receptor'])==t['receptor_sha256']
    assert len(t['ligands'])==96 and not t['failures']
    assert len({l['smiles'] for l in t['ligands']})==96
    assert not {l['smiles'] for l in t['ligands']} & set(selection['excluded_previous_smiles'])
    for l in t['ligands']:
        assert sha(ROOT/l['path'])==l['sha256']
        m=next(Chem.SDMolSupplier(str((ROOT/l['path']).with_suffix('.sdf')),removeHs=False))
        assert m is not None and m.GetConformer().Is3D(), l['id']
        assert len(Chem.GetMolFrags(m))==1
        assert Chem.MolToSmiles(Chem.RemoveHs(m))==l['smiles'], l['id']
    targets.append(dict(target=t['target'],selected=96,actives=sum(l['label']=='active' for l in t['ligands']),
        decoys=sum(l['label']=='decoy' for l in t['ligands']),all_prepared_conformers_marked_3d=True,
        all_hashes_match=True,all_selected_graphs_preserved=True,previous_compound_overlap=0))
result=dict(targets=targets,python=platform.python_version(),rdkit=rdBase.rdkitVersion,
    meeko=getattr(meeko,'__version__','unknown'),
    binaries={p:sha(ROOT/p) for p in ['tmp/docking-pilot/native/vina_1.2.7_win.exe',
        'tmp/vina-tasks/vina_tasks.exe','tmp/vina-resources/compact_single/vina_tasks.wasm']},
    limitations='Graph/coordinate and hash checks do not establish chemically optimal protonation, receptor preparation or benchmark generalization.')
(BASE/'input_verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
