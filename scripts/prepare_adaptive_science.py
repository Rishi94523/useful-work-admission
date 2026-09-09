"""Pre-outcome multi-target selection and independent conformer preparation."""
import gzip,hashlib,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/adaptive-docking';OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from rdkit.Chem import AllChem,Lipinski
from meeko import MoleculePreparation,PDBQTWriterLegacy
import numpy as np

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write_ligand(mol,path):
    text,ok,error=PDBQTWriterLegacy.write_string(MoleculePreparation().prepare(mol)[0])
    if not ok:raise ValueError(error)
    path.write_text(text,encoding='utf-8',newline='\n')
    writer=Chem.SDWriter(str(path.with_suffix('.sdf')));writer.write(mol);writer.close()
    return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path)}

def prepare(target):
    folder=BASE/target;folder.mkdir(parents=True,exist_ok=True);(folder/'ligands').mkdir(exist_ok=True)
    files=[]
    for name in ['actives_final.sdf.gz','decoys_final.sdf.gz','crystal_ligand.mol2','receptor.pdb']:
        p=folder/name;url='https://dude.docking.org/targets/'+target+'/'+name
        if not p.exists():
            if target=='fa10':p.write_bytes((ROOT/'tmp/docking-audit'/name).read_bytes())
            else:
                with urllib.request.urlopen(url,timeout=120) as response:data=response.read(120000001)
                if len(data)>120000000:raise ValueError('Input exceeds download cap')
                p.write_bytes(data)
        files.append({'url':url,'bytes':p.stat().st_size,'sha256':digest(p)})
        print(target,name,p.stat().st_size,flush=True)
    records=[];failures=[];selected_manifest=[];seen=set()
    for label,name in [('active','actives_final.sdf.gz'),('decoy','decoys_final.sdf.gz')]:
        candidates=[]
        with gzip.open(folder/name,'rb') as f:
            for ordinal,m in enumerate(Chem.ForwardSDMolSupplier(f,removeHs=False)):
                if m is None:continue
                smi=Chem.MolToSmiles(Chem.RemoveHs(m));heavy=m.GetNumHeavyAtoms()
                if smi in seen or '.' in smi or not 12<=heavy<=55 or any(a.GetAtomicNum() not in [1,6,7,8,9,15,16,17,35,53] for a in m.GetAtoms()):continue
                seen.add(smi);candidates.append((heavy,ordinal,smi,m))
                if len(candidates)>=96:break
        candidates.sort(key=lambda x:(x[0],x[1]))
        for index in np.linspace(0,len(candidates)-1,8,dtype=int):
            heavy,ordinal,smi,m=candidates[index];identifier=f'{label}_{ordinal:05d}';selected_manifest.append({'id':identifier,'label':label,'smiles':smi})
            try:
                t=time.perf_counter();m=Chem.AddHs(Chem.RemoveHs(m),addCoords=True)
                source=write_ligand(m,folder/'ligands'/(identifier+'_source.pdbqt'))
                independent=Chem.Mol(m);independent.RemoveAllConformers();params=AllChem.ETKDGv3();params.randomSeed=104729+ordinal;params.numThreads=1
                if AllChem.EmbedMolecule(independent,params)!=0:raise ValueError('ETKDG embedding failed')
                opt=AllChem.MMFFOptimizeMolecule(independent,maxIters=200)
                generated=write_ligand(independent,folder/'ligands'/(identifier+'_independent.pdbqt'))
                records.append({'id':identifier,'label':label,'heavy_atoms':heavy,'rotatable_bonds':Lipinski.NumRotatableBonds(m),'source':source,'independent':generated,'mmff_status':opt,'preparation_ms':(time.perf_counter()-t)*1000})
            except Exception as e:failures.append({'id':identifier,'error':str(e)})
    crystal=Chem.MolFromMol2File(str(folder/'crystal_ligand.mol2'),removeHs=False)
    if crystal is None:raise ValueError('Crystal input parse failed')
    crystal=Chem.AddHs(crystal,addCoords=True);reference=write_ligand(crystal,folder/'ligands/crystal_source.pdbqt')
    center=np.array(Chem.RemoveHs(crystal).GetConformer().GetPositions()).mean(axis=0).tolist()
    independent=Chem.Mol(crystal);independent.RemoveAllConformers();params=AllChem.ETKDGv3();params.randomSeed=3571;params.numThreads=1
    if AllChem.EmbedMolecule(independent,params)!=0:raise ValueError('Crystal independent embedding failed')
    AllChem.MMFFOptimizeMolecule(independent,maxIters=200)
    generated=write_ligand(independent,folder/'ligands/crystal_independent.pdbqt')
    records.append({'id':'crystal','label':'redocking','source':reference,'independent':generated,'heavy_atoms':crystal.GetNumHeavyAtoms()})
    lines=[]
    for line in (folder/'receptor.pdb').read_text().splitlines():
        if line.startswith('ATOM'):
            element=''.join(c for c in line[12:16] if c.isalpha())[0]
            if element not in 'HCNOSP':raise ValueError('Unexpected receptor element')
            if element=='H':continue
            line=line.ljust(78);line=line[:76]+element.rjust(2)+line[78:]
        lines.append(line)
    (folder/'receptor_heavy.pdb').write_text('\n'.join(lines)+'\n')
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tmp/docking-audit/deps')
    receptor=folder/'receptor.pdbqt';t=time.perf_counter()
    if not receptor.exists():
        r=subprocess.run([sys.executable,'-m','meeko.cli.mk_prepare_receptor','--read_pdb',str(folder/'receptor_heavy.pdb'),'-o',str(folder/'receptor'),'-p'],env=env,capture_output=True,text=True)
        (folder/'receptor_preparation.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise ValueError('Receptor preparation failed: '+(r.stdout+r.stderr)[-3500:])
    maps=folder/'maps';maps.mkdir(exist_ok=True)
    if not list(maps.glob('*.map')):
        r=subprocess.run([str(ROOT/'tmp/docking-audit/campaign_grid_worker.exe'),str(receptor),*map(str,center),'30','30','30',str(maps/'fa10')],input='QUIT\n',capture_output=True,text=True,timeout=180)
        if r.returncode:raise ValueError(r.stderr)
    return {'target':target,'sources':files,'center':center,'size':[30]*3,'receptor':str(receptor.relative_to(ROOT)).replace('\\','/'),'receptor_sha256':digest(receptor),'preparation_and_maps_ms':(time.perf_counter()-t)*1000,'selection':selected_manifest,'failures':failures,'ligands':records,'maps':[{'name':p.name,'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p),'bytes':p.stat().st_size} for p in sorted(maps.glob('*.map'))]}

OUT.mkdir(parents=True,exist_ok=True);results=[]
existing=json.loads((OUT/'science_inputs.json').read_text())['targets'] if (OUT/'science_inputs.json').exists() else []
for target in ['fa10','hivpr','hs90a','tryb1']:
    cached=next((x for x in existing if x['target']==target),None)
    if cached is not None:results.append(cached);continue
    try:results.append(prepare(target))
    except Exception as e:results.append({'target':target,'preparation_failed':str(e)});print(target,str(e),flush=True)
    (OUT/'science_inputs.json').write_text(json.dumps({'scope':'Pre-outcome size-stratified 8+8 selection from first96 eligible molecules; ETKDG independent coordinates. Target failures retained.','targets':results},indent=2)+'\n')
