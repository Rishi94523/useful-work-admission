"""Prepare a fixed panel with the published ADFR/REDUCE toolchain."""
import collections,gzip,hashlib,json,os,re,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
P=ROOT/'benchmarks/vina_published_validation.json'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def freeze(p,value):
 text=json.dumps(value,indent=2,sort_keys=True)+'\n'
 if p.exists() and p.read_text()!=text:raise ValueError('Frozen record would change: '+p.name)
 p.write_text(text)
def mol2_blocks(text):return ['@<TRIPOS>MOLECULE'+s for s in text.split('@<TRIPOS>MOLECULE')[1:]]
def source_id(block):return block.splitlines()[1].strip().split()[0]
def heavy_xyz(text):
 return np.array([[float(l[i:i+8]) for i in [30,38,46]] for l in text.splitlines() if l.startswith(('ATOM','HETATM')) and l[77:].strip() not in ['H','HD']])
def main():
 cfg=json.loads(P.read_text());base=ROOT/'tmp/vina-published';out=ROOT/cfg['output_directory'];out.mkdir(parents=True,exist_ok=True);suite=base/'ADFRsuite';python=suite/'python.exe';utilities=suite/'Lib/site-packages/AutoDockTools/Utilities24';reduce=suite/'bin/reduce.exe'
 env={**os.environ,'PATH':str(suite/'bin')+os.pathsep+str(suite/'OpenBabel-2.4.1')+os.pathsep+os.environ['PATH'],'BABEL_DATADIR':str(suite/'OpenBabel-2.4.1/data'),'REDUCE_HET_DICT':str(suite/'bin/reduce_wwPDB_het_dict.txt')}
 env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
 def command(args,log,timeout=900):
  r=subprocess.run(list(map(str,args)),cwd=log.parent,env=env,capture_output=True,text=True,timeout=timeout);log.write_text(r.stdout+r.stderr,encoding='utf-8')
  if r.returncode:raise RuntimeError('Preparation command failed: '+log.name)
  return r.stdout
 tool_hashes={name:digest(path) for name,path in {'python':python,'reduce':reduce,'prepare_ligand':utilities/'prepare_ligand4.py','prepare_receptor':utilities/'prepare_receptor4.py','reduce_dictionary':suite/'bin/reduce_wwPDB_het_dict.txt'}.items()}
 freeze(out/'preparation_manifest.json',{'protocol_sha256':digest(P),'tools':tool_hashes,'reduce_args':['-BUILD','-DB','reduce_wwPDB_het_dict.txt'],'receptor_cleanup':'nphs_lps_waters (retain nonprotein chains)','note':'Bundled REDUCE 3.16; paper does not state REDUCE version or expose a pH flag. Use its standard hydrogen/flip behavior, no target-specific pKa optimization.'})
 freeze(out/'preparation_compatibility.json',{'stage':'Before any stock docking','changes':['Strip existing receptor hydrogen atoms before REDUCE -BUILD to prevent duplicate hydrogen coordinates; retain heavy atoms and source files.','Normalize absent hydrogen element fields for MolKit.','Select reference heavy atoms by atomic number rather than assuming RDKit RemoveHs removes every hydrogen.'],'reduce_status':'Accept statuses 0 or 1 only with complete atom output and final heavy-atom validation; preserve stderr and status.','script_sha256':digest(Path(__file__))})
 targets=[]
 for target in cfg['targets']:
  folder=base/target;prepared=folder/'prepared';prepared.mkdir(exist_ok=True);crystal_block=(folder/'crystal_ligand.mol2').read_text();crystal_id=source_id(crystal_block);groups={};selection=[]
  for label in ['active','decoy']:
   name='actives_final.mol2.gz' if label=='active' else 'decoys_final.mol2.gz'
   with gzip.open(folder/name,'rt') as f:blocks=mol2_blocks(f.read())
   classes=collections.defaultdict(list)
   for block in blocks:classes[source_id(block)].append(block)
   candidates=[s for s in classes if s!=crystal_id];ordered=sorted(candidates,key=lambda s:hashlib.sha256((cfg['panel']['salt']+target+':'+label+':'+s).encode()).hexdigest());count=cfg['panel']['actives' if label=='active' else 'decoys'];assert len(ordered)>=count
   for index,source in enumerate(ordered[:count]):
    uid=f'{label}_{index:03d}';groups[uid]=classes[source];selection.append({'id':uid,'source_id':source,'label':label,'states':len(classes[source]),'source_state_sha256':[hashlib.sha256(b.encode()).hexdigest() for b in classes[source]]})
  assert not {s['source_id'] for s in selection if s['label']=='active'}&{s['source_id'] for s in selection if s['label']=='decoy'}
  freeze(out/(target+'_selection.json'),{'selected':selection,'crystal_source_id':crystal_id,'source_hashes':{n:digest(folder/n) for n in ['receptor.pdb','crystal_ligand.mol2','actives_final.mol2.gz','decoys_final.mol2.gz']}})
  failures=[];receptor=prepared/'receptor.pdbqt';rtext='\n'.join(l for l in (folder/'receptor.pdb').read_text().splitlines() if not (l.startswith(('ATOM','HETATM')) and l[17:20].strip() in ['HOH','WAT']))+'\n';clean=prepared/'receptor_no_water.pdb';clean.write_text(rtext)
  try:
   # Rebuild hydrogens once; DUD-E already contains nonstandard named H atoms.
   trimmed=prepared/'receptor_heavy.pdb'
   trimmed.write_text('\n'.join(l for l in rtext.splitlines() if not (l.startswith(('ATOM','HETATM')) and (l[76:78].strip()=='H' or (not l[76:78].strip() and l[12:16].strip().lstrip('0123456789').startswith('H')))))+'\n')
   reduced=prepared/'receptor_rebuilt.pdb'
   if not reduced.exists():
    result=subprocess.run([str(reduce),'-BUILD','-DB',str(suite/'bin/reduce_wwPDB_het_dict.txt'),str(trimmed)],cwd=prepared,env=env,capture_output=True,text=True,timeout=900)
    (prepared/'reduce_rebuilt.log').write_text('returncode='+str(result.returncode)+'\n'+result.stderr)
    # REDUCE can return a nonzero status after producing a complete structure.
    assert result.returncode in (0,1),'REDUCE execution failed'
    assert sum(l.startswith(('ATOM','HETATM')) for l in result.stdout.splitlines())>=sum(l.startswith(('ATOM','HETATM')) for l in trimmed.read_text().splitlines()),'Incomplete REDUCE output'
    reduced.write_text(result.stdout)
   # DUD-E sometimes omits PDB element fields on names such as HN12.
   # Supply the unambiguous hydrogen element without moving/renaming atoms.
   normalized=prepared/'receptor_reduce_elements.pdb';normalized_lines=[]
   for line in reduced.read_text().splitlines():
    if line.startswith(('ATOM','HETATM')) and line[12:16].strip().lstrip('0123456789').startswith('H') and not line[76:78].strip():line=line.ljust(78)[:76]+' H'+line.ljust(78)[78:]
    normalized_lines.append(line)
   normalized.write_text('\n'.join(normalized_lines)+'\n')
   if not receptor.exists():command([python,utilities/'prepare_receptor4.py','-r',normalized,'-o',receptor,'-U','nphs_lps_waters'],prepared/'receptor.log')
   lines=receptor.read_text().splitlines();metals=[]
   for i,l in enumerate(lines):
    if l.startswith(('ATOM','HETATM')) and l[77:].strip() in ['Zn','Mg','Mn','Ca','Fe','Cu','Co','Ni']:
     metals.append({'atom':l[12:16].strip(),'type':l[77:].strip()});lines[i]=l[:70]+f'{2.0:6.3f}'+l[76:]
   receptor.write_text('\n'.join(lines)+'\n')
   source_heavy=sum(l.startswith(('ATOM','HETATM')) and not l[12:16].strip().startswith('H') for l in rtext.splitlines());assert len(heavy_xyz(receptor.read_text()))==source_heavy,'Receptor heavy atom loss'
  except Exception as e:failures.append({'scope':'receptor','error':str(e)});metals=[]
  ligands=[];crystal=None
  for item in [{'id':'crystal','source_id':crystal_id,'label':'crystal','states':1}]+selection:
   for index,block in enumerate([crystal_block] if item['id']=='crystal' else groups[item['id']]):
    sid=item['id']+f'_s{index:03d}';mol2=prepared/(sid+'.mol2');pdbqt=prepared/(sid+'.pdbqt');mol2.write_text(block)
    try:
     if not pdbqt.exists():command([python,utilities/'prepare_ligand4.py','-l',mol2,'-o',pdbqt],prepared/(sid+'.log'),120)
     m=Chem.MolFromMol2Block(block,removeHs=False);assert m is not None,'Source MOL2 parse failed';xyz=heavy_xyz(pdbqt.read_text());source=m.GetConformer().GetPositions()[[a.GetIdx() for a in m.GetAtoms() if a.GetAtomicNum()>1]];assert len(xyz)==len(source) and np.isfinite(xyz).all(),'Ligand heavy atom count/coordinates'
     distance=np.linalg.norm(source[:,None]-xyz[None],axis=-1);assert max(distance.min(0).max(),distance.min(1).max())<.02,'Ligand heavy coordinates changed'
     row={'id':sid,'compound_id':item['id'],'source_id':item['source_id'],'label':item['label'],'path':pdbqt.relative_to(ROOT).as_posix(),'sha256':digest(pdbqt),'mol2_sha256':digest(mol2)}
     if item['id']=='crystal':
      writer=Chem.SDWriter(str(pdbqt.with_suffix('.sdf')));writer.write(m);writer.close();crystal=row;center=source.mean(0).tolist()
     else:ligands.append(row)
    except Exception as e:failures.append({'scope':'ligand','id':sid,'compound_id':item['id'],'error':str(e)})
  targets.append({'target':target,'receptor':receptor.relative_to(ROOT).as_posix(),'receptor_sha256':digest(receptor) if receptor.exists() else None,'center':center if crystal else None,'size':cfg['preparation']['box_size_A'],'crystal':crystal,'ligands':ligands,'compounds':selection,'failures':failures,'metals':metals})
  (out/'inputs.json').write_text(json.dumps({'protocol_sha256':digest(P),'stock_sha256':digest(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'targets':targets},indent=2)+'\n');print(target,'compounds',len(selection),'states',len(ligands),'failures',failures,flush=True)
if __name__=='__main__':main()
