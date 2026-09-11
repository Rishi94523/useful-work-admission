"""Stock-first redocking controls; preserve all failures and exact inputs."""
import hashlib,json,re,subprocess,sys,time,urllib.request
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from rdkit.Chem import rdMolAlign
BASE=ROOT/'tmp/vina-validation';OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10'
BASE.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def coords(text):
 return np.array([[float(line[i:i+8]) for i in [30,38,46]] for line in text.split('ENDMDL')[0].splitlines() if line.startswith(('ATOM','HETATM')) and line[77:].strip() not in ['H','HD','G0','G1','G2','G3']])
def quality(ligand,sdf,text):
 ref=Chem.RemoveHs(Chem.SDMolSupplier(str(sdf),removeHs=False)[0]);xyz=ref.GetConformer().GetPositions();initial=coords(ligand.read_text());_,order=linear_sum_assignment(np.linalg.norm(xyz[:,None]-initial[None],axis=-1))
 assert np.max(np.linalg.norm(xyz-initial[order],axis=1))<.02,'PDBQT/SDF mapping failed'
 values=[]
 for pose in text.split('ENDMDL'):
  if 'ATOM' not in pose:continue
  probe=Chem.Mol(ref)
  for i,p in enumerate(coords(pose)[order]):probe.GetConformer().SetAtomPosition(i,tuple(map(float,p)))
  values.append(float(rdMolAlign.CalcRMS(probe,ref,maxMatches=10000)))
 return {'top_rmsd_A':values[0],'best_rmsd_A':min(values),'all_rmsd_A':values,'score':float(re.search(r'REMARK VINA RESULT:\s+([-\d.]+)',text).group(1)),'redocking_gate':values[0]<=2}
def inputs():
 folder=BASE/'1iep';folder.mkdir(exist_ok=True);files=[]
 for name in ['1iep_receptor.pdbqt','1iep_ligand.pdbqt','1iep_ligand.sdf','1iep_receptor.box.txt']:
  p=folder/name;url='https://raw.githubusercontent.com/ccsb-scripps/AutoDock-Vina/v1.2.7/example/basic_docking/solution/'+name
  if not p.exists():
   with urllib.request.urlopen(url,timeout=90) as response:p.write_bytes(response.read(5000000))
  files.append({'name':name,'url':url,'sha256':digest(p)})
 config={k.strip():float(v) for line in (folder/'1iep_receptor.box.txt').read_text().splitlines() if '=' in line for k,v in [line.split('=')]}
 targets=[{'target':'1iep','receptor':str(folder/'1iep_receptor.pdbqt'),'ligand':str(folder/'1iep_ligand.pdbqt'),'sdf':str(folder/'1iep_ligand.sdf'),'center':[config['center_'+x] for x in 'xyz'],'size':[config['size_'+x] for x in 'xyz'],'sources':files}]
 for t in json.loads((ROOT/'docs/evaluation/adaptive_docking_2026-09-08/science_inputs.json').read_text())['targets']:
  if t.get('preparation_failed'):continue
  ligand=ROOT/next(l for l in t['ligands'] if l['id']=='crystal')['source']['path']
  targets.append({'target':t['target'],'receptor':str(ROOT/t['receptor']),'ligand':str(ligand),'sdf':str(ligand.with_suffix('.sdf')),'center':t['center'],'size':t['size']})
 for t in targets:t['hashes']={key:digest(Path(t[key])) for key in ['receptor','ligand','sdf']}
 (OUT/'inputs.json').write_text(json.dumps(targets,indent=2)+'\n');return targets
if __name__=='__main__':
 targets=inputs()
 if '--download-only' in sys.argv:print('inputs ready');sys.exit()
 path=OUT/'stock_controls.json';rows=json.loads(path.read_text()) if path.exists() else []
 for t in targets:
  for seed in [104729,130363,155921]:
   if any(r['target']==t['target'] and r['seed']==seed for r in rows):continue
   dest=BASE/(t['target']+'_'+str(seed)+'.pdbqt');args=[str(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'--receptor',t['receptor'],'--ligand',t['ligand'],'--cpu','1','--seed',str(seed),'--exhaustiveness','32','--num_modes','9','--energy_range','1000','--out',str(dest)]
   for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['center'][i]),'--size_'+x,str(t['size'][i])]
   start=time.perf_counter();row={'target':t['target'],'seed':seed,'exhaustiveness':32,'hashes':t['hashes'],'args':args}
   try:
    r=subprocess.run(args,capture_output=True,text=True,timeout=1200);row.update(returncode=r.returncode,wall_ms=(time.perf_counter()-start)*1000,stdout=r.stdout,stderr=r.stderr)
    if r.returncode==0:row.update(quality(Path(t['ligand']),Path(t['sdf']),dest.read_text()),pose=dest.read_text())
   except subprocess.TimeoutExpired:row.update(error='1200 second timeout',wall_ms=(time.perf_counter()-start)*1000)
   rows.append(row);path.write_text(json.dumps(rows,indent=2)+'\n');print(t['target'],seed,row.get('top_rmsd_A'),row.get('wall_ms'),flush=True)
