"""Prepare disjoint stock-only development/heldout panels and receptor audit."""
import collections,gzip,hashlib,json,os,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem,RDLogger
from rdkit.Chem.MolStandardize import rdMolStandardize
from meeko import MoleculePreparation,PDBQTWriterLegacy
RDLogger.DisableLog('rdApp.warning')
P=ROOT/'benchmarks/vina_stock_diagnostic.json';cfg=json.loads(P.read_text());OUT=ROOT/cfg['output_directory'];BASE=ROOT/'tmp/vina-stock-diagnostic';OUT.mkdir(parents=True,exist_ok=True)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def parent(m):
 m=rdMolStandardize.Cleanup(Chem.RemoveHs(m));m=rdMolStandardize.Uncharger().uncharge(m);m=rdMolStandardize.TautomerEnumerator().Canonicalize(m);Chem.RemoveStereochemistry(m);return Chem.MolToSmiles(m)
def atom_rows(path):
 return [{'name':l[12:16].strip(),'res':l[17:20].strip(),'key':l[21:27],'xyz':np.array([float(l[i:i+8]) for i in [30,38,46]]),'type':l[77:].strip()} for l in path.read_text().splitlines() if l.startswith(('ATOM','HETATM'))]
def hist_state(rows,key):
 r=[a for a in rows if a['key']==key];sites={a['name']:a for a in r if a['name'] in ('ND1','NE2')};attached=[]
 for name,a in sites.items():
  if any(h['name'].startswith('H') and np.linalg.norm(h['xyz']-a['xyz'])<1.3 for h in r):attached.append(name)
 return 'HIP' if len(attached)==2 else 'HID' if attached==['ND1'] else 'HIE' if attached==['NE2'] else None
def prepare_mol(m,path):
 path.parent.mkdir(parents=True,exist_ok=True);m=Chem.AddHs(Chem.RemoveHs(m),addCoords=True)
 text,ok,error=PDBQTWriterLegacy.write_string(MoleculePreparation().prepare(m)[0])
 if not ok:raise ValueError(error)
 if path.exists() and path.read_text()!=text:raise ValueError('Prepared input would change')
 path.write_text(text,encoding='utf-8',newline='\n');w=Chem.SDWriter(str(path.with_suffix('.sdf')));w.write(m);w.close();return {'path':path.relative_to(ROOT).as_posix(),'sha256':digest(path),'smiles':Chem.MolToSmiles(Chem.RemoveHs(m)),'formal_charge':Chem.GetFormalCharge(m),'heavy_atoms':m.GetNumHeavyAtoms()}

old=json.loads((ROOT/'local-research/ranking-extension-2026-09-14/large_inputs.json').read_text());targets=[];audits=[]
for name in cfg['targets']:
 src=ROOT/'tmp/vina-extension'/name;folder=BASE/name;folder.mkdir(parents=True,exist_ok=True);t=next(t for t in old['targets'] if t['target']==name)
 crystal=Chem.MolFromMol2File(str(src/'crystal_ligand.mol2'),removeHs=False);xyz=Chem.RemoveHs(crystal).GetConformer().GetPositions();reference=prepare_mol(crystal,folder/'crystal.pdbqt')
 source=atom_rows(src/'receptor.pdb');legacy=atom_rows(src/'receptor.pdbqt');changes=[];mapping={}
 for key in sorted({a['key'] for a in source if a['res'] in ('HIS','HID','HIE','HIP')}):
  atoms=[a for a in source if a['key']==key];original=hist_state(source,key);converted=hist_state(legacy,key);near=min(float(np.linalg.norm(a['xyz']-xyz,axis=1).min()) for a in atoms if not a['name'].startswith('H'))
  changes.append({'residue':key.strip(),'source_name':atoms[0]['res'],'source_state_from_H':original,'legacy_state_from_H':converted,'min_crystal_distance_A':near})
  if atoms[0]['res']=='HIS' and original:mapping[key]=original
 lines=[]
 for line in (src/'receptor_heavy.pdb').read_text().splitlines():
  if line.startswith(('ATOM','HETATM')) and line[21:27] in mapping:line=line[:17]+mapping[line[21:27]]+line[20:]
  lines.append(line)
 corrected=folder/'source_state.pdb';corrected.write_text('\n'.join(lines)+'\n')
 dest=folder/'source_state.pdbqt'
 if not dest.exists():
  r=subprocess.run([sys.executable,'-m','meeko.cli.mk_prepare_receptor','--read_pdb',str(corrected),'-o',str(folder/'source_state'),'-p'],env={**os.environ,'PYTHONPATH':str(ROOT/'tmp/docking-audit/deps')},capture_output=True,text=True)
  (folder/'source_state_preparation.log').write_text(r.stdout+r.stderr)
  if r.returncode:raise RuntimeError(r.stderr[-1000:])
 new=atom_rows(dest)
 for item in changes:
  key=next(k for k in {a['key'] for a in source} if k.strip()==item['residue']);item['revised_state_from_H']=hist_state(new,key)
  if key in mapping:assert item['revised_state_from_H']==mapping[key]
 heavy_source=[a for a in source if not a['name'].startswith('H')];heavy_new=[a for a in new if not a['name'].startswith('H')]
 # Nearest-coordinate checks also tolerate documented cofactor atom-name aliases.
 distances=np.linalg.norm(np.array([a['xyz'] for a in heavy_source])[:,None]-np.array([a['xyz'] for a in heavy_new])[None],axis=-1)
 heavy_change=max(float(distances.min(0).max()),float(distances.min(1).max()))
 if heavy_change>.02 or len(heavy_source)!=len(heavy_new):raise ValueError('Receptor heavy geometry changed')
 audit={'target':name,'histidines':changes,'cofactor_residues':sorted({a['res'] for a in source if a['res'] not in 'ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL HID HIE HIP'.split()}),'heavy_atoms':len(heavy_source),'max_heavy_coordinate_change_A':heavy_change,'legacy_box_volume':27000,'crystal_span_A':np.ptp(xyz,axis=0).tolist()}
 blocked={parent(crystal)}
 # All existing selection files for this target, including failed panels.
 selection_paths=list((ROOT/'docs/evaluation').glob('**/'+name+'_selection.json'))+list((ROOT/'local-research/ranking-extension-2026-09-14').glob(name+'_selection.json'))
 for path in selection_paths:
  for row in json.loads(path.read_text()).get('selected',[]):blocked.add(parent(Chem.MolFromSmiles(row['smiles'])))
 legacy_science=json.loads((ROOT/'docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json').read_text())
 for previous in legacy_science['targets']:
  if previous['target']==name:
   for row in previous.get('selection',[]):blocked.add(parent(Chem.MolFromSmiles(row['smiles'])))
 all_candidates={};failed_parse=collections.Counter()
 for label,file in [('active','actives_final.sdf.gz'),('decoy','decoys_final.sdf.gz')]:
  count=0
  with gzip.open(src/file,'rb') as stream:
   for ordinal,m in enumerate(Chem.ForwardSDMolSupplier(stream,removeHs=False)):
    if m is None:failed_parse[label]+=1;continue
    if len(Chem.GetMolFrags(m))!=1 or not 12<=m.GetNumHeavyAtoms()<=55 or any(a.GetAtomicNum() not in [1,6,7,8,9,15,16,17,35,53] for a in m.GetAtoms()) or not m.GetNumConformers() or not np.isfinite(m.GetConformer().GetPositions()).all():continue
    key=parent(m)
    if key in blocked:continue
    smi=Chem.MolToSmiles(Chem.RemoveHs(m));entry={'id':f'{label}_{ordinal:05d}','label':label,'parent':key,'smiles':smi,'mol':m}
    if key in all_candidates:
     if all_candidates[key]['label']!=label:all_candidates[key]['conflict']=True
     continue
    all_candidates[key]=entry;count+=1
    if count>=cfg['split']['candidate_limit_per_class']:break
 selected={'development':[],'heldout':[]}
 for label in ['active','decoy']:
  candidates=[v for v in all_candidates.values() if v['label']==label and not v.get('conflict')]
  for split in ['development','heldout']:
   number=cfg['split'][split+'_'+('actives' if label=='active' else 'decoys')];salt=cfg['split'][split+'_salt'];ordered=sorted(candidates,key=lambda x:hashlib.sha256((salt+x['parent']).encode()).hexdigest())
   if len(ordered)<number:raise ValueError('Insufficient independent parents')
   chosen=ordered[:number];selected[split].extend(chosen);used={x['parent'] for x in chosen};candidates=[x for x in candidates if x['parent'] not in used]
 dev={x['parent'] for x in selected['development']};held={x['parent'] for x in selected['heldout']};assert not dev&held and not (dev|held)&blocked
 selection={k:[{a:b for a,b in x.items() if a!='mol'} for x in v] for k,v in selected.items()}
 selection.update(excluded_parent_count=len(blocked),source_hashes={file:digest(src/file) for file in ['actives_final.sdf.gz','decoys_final.sdf.gz','receptor.pdb','crystal_ligand.mol2']},parse_failures=dict(failed_parse))
 path=OUT/(name+'_split.json');text=json.dumps(selection,indent=2)+'\n'
 if path.exists() and path.read_text()!=text:raise ValueError('Split changed')
 path.write_text(text);prepared={};failures=[]
 for split,items in selected.items():
  prepared[split]=[]
  for item in items:
   try:prepared[split].append({**{k:v for k,v in item.items() if k!='mol'},**prepare_mol(item['mol'],folder/split/(item['id']+'.pdbqt'))})
   except Exception as e:failures.append({'split':split,'id':item['id'],'error':str(e)})
 row={'target':name,'receptors':{'legacy':t['receptor'],'source_state':dest.relative_to(ROOT).as_posix()},'boxes':{'legacy30':{'center':t['center'],'size':[30]*3},'crystal_site':{'center':((xyz.max(0)+xyz.min(0))/2).tolist(),'size':np.maximum(20,np.ptp(xyz,axis=0)+12).tolist()}},'crystal':reference,'splits':prepared,'failures':failures,'selection_sha256':digest(path)}
 row['receptor_hashes']={k:digest(ROOT/v) for k,v in row['receptors'].items()};targets.append(row);audits.append(audit)
 (OUT/'inputs.json').write_text(json.dumps({'protocol_sha256':digest(P),'targets':targets,'stock_sha256':digest(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe')},indent=2)+'\n');(OUT/'preparation_audit.json').write_text(json.dumps(audits,indent=2)+'\n');print(name,'prepared',len(prepared['development']),len(prepared['heldout']),'failures',len(failures),flush=True)
