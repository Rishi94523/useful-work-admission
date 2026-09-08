"""Prepare a deterministic, heterogeneous public screening pilot with Meeko/RDKit."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'
sys.path.insert(0,str(BASE/'deps'))
from rdkit import Chem
from rdkit.Chem import AllChem,Descriptors,Lipinski
from meeko import MoleculePreparation,PDBQTWriterLegacy
import numpy as np


def main():
    folder=BASE/'ligands';folder.mkdir(exist_ok=True)
    records=[];failures=[];seen=set()
    for label,name in [('active','actives_final.sdf.gz'),('decoy','decoys_final.sdf.gz')]:
        candidates=[]
        with gzip.open(BASE/name,'rb') as f:
            for ordinal,mol in enumerate(Chem.ForwardSDMolSupplier(f,removeHs=False)):
                if mol is None:continue
                smi=Chem.MolToSmiles(Chem.RemoveHs(mol))
                if smi in seen or '.' in smi:continue
                heavy=mol.GetNumHeavyAtoms()
                if not 12<=heavy<=55 or any(a.GetAtomicNum() not in [1,6,7,8,9,15,16,17,35,53] for a in mol.GetAtoms()):continue
                seen.add(smi);candidates.append((heavy,ordinal,smi,mol))
                if len(candidates)>=96:break
        # Spread molecular sizes; selection is fixed before docking outcomes.
        candidates.sort(key=lambda r:(r[0],r[1]));selected=[candidates[i] for i in np.linspace(0,len(candidates)-1,16,dtype=int)]
        for heavy,ordinal,smi,mol in selected:
            begin=time.perf_counter();identifier=f'{label}_{ordinal:05d}'
            try:
                mol=Chem.AddHs(Chem.RemoveHs(mol),addCoords=True)
                # Source pose retained as conformer 0; additional conformers are
                # generated without using crystal pose or docking scores.
                source=np.array(mol.GetConformer().GetPositions());generated=Chem.Mol(mol);generated.RemoveAllConformers()
                params=AllChem.ETKDGv3();params.randomSeed=104729+ordinal;params.numThreads=1;params.pruneRmsThresh=.5
                ids=list(AllChem.EmbedMultipleConfs(generated,numConfs=3,params=params))
                if ids:AllChem.MMFFOptimizeMoleculeConfs(generated,numThreads=1,maxIters=100)
                banks=[source]+[np.array(generated.GetConformer(i).GetPositions()) for i in ids]
                setup=MoleculePreparation().prepare(mol)[0];pdbqt,ok,error=PDBQTWriterLegacy.write_string(setup)
                if not ok:raise ValueError(error)
                (folder/(identifier+'.pdbqt')).write_text(pdbqt)
                writer=Chem.SDWriter(str(folder/(identifier+'.sdf')));writer.write(mol);writer.close()
                heavy_ids=[a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum()!=1]
                np.save(folder/(identifier+'.conformers.npy'),np.array(banks)[:,heavy_ids,:])
                records.append({'id':identifier,'label':label,'source_ordinal':ordinal,'source_name':mol.GetProp('_Name') if mol.HasProp('_Name') else '', 'smiles':smi,'heavy_atoms':heavy,'rotatable_bonds':Lipinski.NumRotatableBonds(mol),'conformers':len(banks),'molecular_weight':Descriptors.MolWt(mol),'pdbqt_sha256':hashlib.sha256(pdbqt.encode()).hexdigest(),'preparation_ms':(time.perf_counter()-begin)*1000})
                print(identifier,heavy,len(banks),flush=True)
            except Exception as error:failures.append({'id':identifier,'error':str(error)})
    crystal=Chem.MolFromMol2File(str(BASE/'crystal_ligand.mol2'),removeHs=False)
    if crystal is None:raise ValueError('Reference ligand could not be parsed')
    crystal=Chem.AddHs(crystal,addCoords=True);setup=MoleculePreparation().prepare(crystal)[0];pdbqt,ok,error=PDBQTWriterLegacy.write_string(setup)
    if not ok:raise ValueError(error)
    (folder/'crystal.pdbqt').write_text(pdbqt);writer=Chem.SDWriter(str(folder/'crystal.sdf'));writer.write(crystal);writer.close()
    center=np.array(crystal.GetConformer().GetPositions())[[a.GetIdx() for a in crystal.GetAtoms() if a.GetAtomicNum()!=1]].mean(axis=0)
    evidence={'selection':'16 size-stratified unique molecules per label from first 96 eligible entries, before docking outcomes. DUD-E decoys are presumed nonbinders, not experimental negatives. Single-target pilot, not full enrichment validation.','receptor':'DUD-E FA10','box_center':center.tolist(),'box_size':[24,24,24],'records':records,'failures':failures}
    (OUT/'ligands.json').write_text(json.dumps(evidence,indent=2)+'\n')
    # Historical PDB lacks element columns. Infer standard protein elements from
    # ATOM names only; do not guess heteroatom identities.
    lines=[]
    for line in (BASE/'receptor.pdb').read_text().splitlines():
        if line.startswith('ATOM'):
            element=''.join(c for c in line[12:16] if c.isalpha())[0]
            if element not in 'HCNOSP':raise ValueError('Unexpected protein element')
            line=line.ljust(78);line=line[:76]+element.rjust(2)+line[78:]
        lines.append(line)
    (BASE/'receptor_elements.pdb').write_text('\n'.join(lines)+'\n')
    # Legacy polar hydrogens caused spurious bonds around disulfides in Meeko.
    # Retain every heavy atom; rebuild H from Meeko residue templates.
    (BASE/'receptor_heavy.pdb').write_text('\n'.join(x for x in lines if not (x.startswith('ATOM') and x[76:78].strip()=='H'))+'\n')
    print(json.dumps({'prepared':len(records),'failed':failures,'box_center':center.tolist()}))


if __name__=='__main__':main()
