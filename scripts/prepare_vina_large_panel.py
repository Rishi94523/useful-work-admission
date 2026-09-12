"""Outcome-blind selection, original DUD-E conformers, explicit preparation failures."""
import gzip,hashlib,json,os,shutil,subprocess,sys,urllib.request
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from meeko import MoleculePreparation,PDBQTWriterLegacy
BASE=ROOT/'tmp/vina-followup';OUT=ROOT/'docs/evaluation/vina_followup_2026-09-12';OUT.mkdir(parents=True,exist_ok=True)
old=json.loads((ROOT/'docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json').read_text())['targets']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(m,p):
 text,ok,error=PDBQTWriterLegacy.write_string(MoleculePreparation().prepare(m)[0])
 if not ok:raise ValueError(error)
 p.write_text(text,encoding='utf-8',newline='\n');w=Chem.SDWriter(str(p.with_suffix('.sdf')));w.write(m);w.close()
rows=[]
for target in ['fa10','tryb1','esr1']:
 folder=BASE/target;folder.mkdir(parents=True,exist_ok=True);(folder/'ligands').mkdir(exist_ok=True);sources=[]
 for name in ['actives_final.sdf.gz','decoys_final.sdf.gz','crystal_ligand.mol2','receptor.pdb']:
  p=folder/name;url='https://dude.docking.org/targets/'+target+'/'+name
  if not p.exists():
   cached=ROOT/'tmp/adaptive-docking'/target/name
   if cached.exists():shutil.copyfile(cached,p)
   else:
    with urllib.request.urlopen(url,timeout=120) as r:data=r.read(120000001)
    if len(data)>120000000:raise ValueError('Download limit')
    p.write_bytes(data)
  sources.append({'url':url,'sha256':digest(p),'bytes':p.stat().st_size})
 previous=next((t for t in old if t['target']==target),None);exclude=set(x['smiles'] for x in previous.get('selection',[])) if previous else set();selected=[];seen=set()
 for label,name,count in [('active','actives_final.sdf.gz',32),('decoy','decoys_final.sdf.gz',64)]:
  candidates=[]
  with gzip.open(folder/name,'rb') as f:
   for ordinal,m in enumerate(Chem.ForwardSDMolSupplier(f,removeHs=False)):
    if m is None:continue
    smi=Chem.MolToSmiles(Chem.RemoveHs(m))
    if smi in seen or smi in exclude or '.' in smi or not 12<=m.GetNumHeavyAtoms()<=55 or any(a.GetAtomicNum() not in [1,6,7,8,9,15,16,17,35,53] for a in m.GetAtoms()) or not m.GetNumConformers() or not np.isfinite(m.GetConformer().GetPositions()).all():continue
    seen.add(smi);key=hashlib.sha256(('vina-followup-2026-09-12:'+smi).encode()).hexdigest();candidates.append((key,ordinal,smi,m))
    if len(candidates)>=2000:break
  assert len(candidates)>=count,(target,label,len(candidates))
  for key,ordinal,smi,m in sorted(candidates,key=lambda x:x[0])[:count]:selected.append({'id':f'{label}_{ordinal:05d}','label':label,'smiles':smi,'selection_hash':key,'mol':m})
 selection=[{k:v for k,v in x.items() if k!='mol'} for x in selected];(OUT/(target+'_selection.json')).write_text(json.dumps({'sources':sources,'excluded_previous_smiles':sorted(exclude),'selected':selection},indent=2)+'\n')
 failures=[];ligands=[]
 for item in selected:
  m=Chem.AddHs(Chem.RemoveHs(item['mol']),addCoords=True);p=folder/'ligands'/(item['id']+'.pdbqt')
  try:
   if not p.exists():write(m,p)
   ligands.append({**{k:v for k,v in item.items() if k!='mol'},'path':p.relative_to(ROOT).as_posix(),'sha256':digest(p)})
  except Exception as e:failures.append({'id':item['id'],'error':str(e)})
 receptor=folder/'receptor.pdbqt'
 if not receptor.exists():
  if previous and not previous.get('preparation_failed'):shutil.copyfile(ROOT/previous['receptor'],receptor)
  else:
   lines=[]
   for line in (folder/'receptor.pdb').read_text().splitlines():
    if line.startswith('ATOM'):
     element=''.join(c for c in line[12:16] if c.isalpha())[0]
     if element=='H':continue
     if element not in 'CNOSP':raise ValueError('Receptor element')
     line=line.ljust(78);line=line[:76]+element.rjust(2)+line[78:]
    lines.append(line)
   heavy=folder/'receptor_heavy.pdb';heavy.write_text('\n'.join(lines)+'\n');env={**os.environ,'PYTHONPATH':str(ROOT/'tmp/docking-audit/deps')}
   r=subprocess.run([sys.executable,'-m','meeko.cli.mk_prepare_receptor','--read_pdb',str(heavy),'-o',str(folder/'receptor'),'-p'],env=env,capture_output=True,text=True);(folder/'receptor_preparation.log').write_text(r.stdout+r.stderr)
   if r.returncode:raise RuntimeError(r.stderr[-2000:])
 crystal=Chem.MolFromMol2File(str(folder/'crystal_ligand.mol2'),removeHs=False);center=Chem.RemoveHs(crystal).GetConformer().GetPositions().mean(axis=0).tolist()
 rows.append({'target':target,'receptor':receptor.relative_to(ROOT).as_posix(),'receptor_sha256':digest(receptor),'center':center,'size':[30]*3,'ligands':ligands,'failures':failures,'selection_sha256':digest(OUT/(target+'_selection.json'))})
 (OUT/'large_inputs.json').write_text(json.dumps({'targets':rows,'scope':'Preselected32+64 per target, supplied DUD-E conformations, previous panel compounds excluded. Failed selected preparations are not replaced.'},indent=2)+'\n');print(target,len(ligands),'ready;',len(failures),'failures',flush=True)
