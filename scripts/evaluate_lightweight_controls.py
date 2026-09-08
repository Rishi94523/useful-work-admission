"""Uncapped Vina control and an explicitly bound-conformer redocking control."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));BASE=ROOT/'tmp/docking-audit';sys.path.insert(0,str(BASE/'deps'))
from rdkit import Chem
from rdkit.Chem import rdMolAlign
from research.lightweight_docking import Assets
from scripts.evaluate_lightweight_science import auc
OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07';a=Assets(BASE/'assets');rec=json.loads((OUT/'ligands.json').read_text());folder=BASE/'science'
p=subprocess.Popen([str(BASE/'campaign_grid_worker.exe'),str(BASE/'receptor.pdbqt'),*map(str,rec['box_center']),'30','30','30',str(BASE/'maps/fa10')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def reply():
    while True:
        line=p.stdout.readline()
        if not line:raise RuntimeError('Native process stopped')
        if line.startswith('{'):return json.loads(line)
def call(mode,path,extra=''):
    p.stdin.write(f'{mode} "{Path(path).as_posix()}" {extra}\n');p.stdin.flush();r=reply()
    if r.get('ok') is False:raise ValueError(r)
    return r
reply();results=[];checkpoint=OUT/'uncapped_progress.json'
if checkpoint.exists():results=json.loads(checkpoint.read_text())
try:
    for l in a.meta['ligands']:
        if any(x['id']==l['id'] for x in results):continue
        source=BASE/'ligands'/(l['id']+'.pdbqt');out=folder/(l['id']+'_uncapped.pdbqt');t=time.perf_counter();call('LOAD',source);load_ms=(time.perf_counter()-t)*1000
        r=call('DOCK',source,f'1 0 "{out.as_posix()}"');results.append({'id':l['id'],'label':l['label'],'exhaustiveness':1,'max_evals':0,'load_ms':load_ms,'output_bytes':out.stat().st_size,**r})
        checkpoint.write_text(json.dumps(results,indent=2)+'\n');print(l['id'],round(r['compute_and_pose_prepare_ms']),r['score'],flush=True)
    source=BASE/'ligands/crystal.pdbqt';meta=call('META',source);xyz=np.array([atom['xyz'] for atom in meta['atoms']]);native_types=[atom['type'] for atom in meta['atoms']]
    l={'id':'crystal','types':[a.meta['map_types'].index(t) for t in native_types],'conformers_milli':[np.floor((xyz-xyz.mean(axis=0))*1000+.5).astype(int).tolist()],'offset':104729}
    a.ligands['crystal']=l;best=2**63-1;best_index=None;best_rmsd=1e9;ref=Chem.RemoveHs(Chem.SDMolSupplier(str(BASE/'ligands/crystal.sdf'),removeHs=False)[0]);ref_xyz=np.array(ref.GetConformer().GetPositions());_,col=linear_sum_assignment(np.linalg.norm(ref_xyz[:,None,:]-xyz[None,:,:],axis=-1))
    begin=time.perf_counter()
    for start in range(0,65536,4096):
        values=a.evaluate('crystal',start,4096).astype(np.int64).sum(axis=1);ix=int(np.argmin(values))
        if int(values[ix])<best:best=int(values[ix]);best_index=start+ix
        poses=a.positions('crystal',np.arange(start,start+4096))/1000
        best_rmsd=min(best_rmsd,float(np.sqrt(np.mean(np.sum((poses[:,col,:]-ref_xyz)**2,axis=-1),axis=-1)).min()))
    search_ms=(time.perf_counter()-begin)*1000
    def rmsd(positions):
        mol=Chem.Mol(ref)
        for i,pos in enumerate(positions):mol.GetConformer().SetAtomPosition(i,tuple(map(float,pos)))
        return float(rdMolAlign.CalcRMS(mol,ref,maxMatches=10000))
    selected=a.positions('crystal',[best_index])[0][col]/1000;coarse_rmsd=rmsd(selected)
    call('LOAD',source);out=folder/'crystal_uncapped.pdbqt';native=call('DOCK',source,f'4 0 "{out.as_posix()}"')
    def heavy(text):return np.array([[float(line[k:k+8]) for k in [30,38,46]] for line in text.splitlines() if line.startswith(('ATOM','HETATM')) and line[77:].strip() not in ('H','HD','G0','G1','G2','G3')])
    original=heavy(source.read_text());predicted=heavy(out.read_text());_,pc=linear_sum_assignment(np.linalg.norm(ref_xyz[:,None,:]-original[None,:,:],axis=-1));native_rmsd=rmsd(predicted[pc])
    control={'scope':'Redocking with known bound conformer. This is an optimistic conformational-control experiment, not independently generated ligand conformers or virtual screening. The finite bank uses random rotations, never inserts the reference orientation explicitly. Selected-pose RMSD uses RDKit symmetry-aware CalcRMS without alignment; bank coverage minimum is atom-index RMSD.','finite_bank_poses':65536,'coarse_best_energy':best/10000,'coarse_best_index':best_index,'coarse_selected_symmetry_rmsd_A':coarse_rmsd,'bank_minimum_atom_index_rmsd_A':best_rmsd,'coarse_search_and_coverage_ms':search_ms,'vina':native,'vina_exhaustiveness':4,'vina_max_evals':0,'vina_selected_symmetry_rmsd_A':native_rmsd}
finally:p.stdin.write('QUIT\n');p.stdin.flush();p.stdin.close();p.wait(timeout=10)
labels=np.array([x['label']=='active' for x in results]);energies=np.array([x['score'] for x in results]);rng=np.random.default_rng(104729);samples=[]
for _ in range(2000):
    indices=np.r_[rng.choice(np.where(labels)[0],16),rng.choice(np.where(~labels)[0],16)];samples.append(auc(labels[indices],energies[indices]))
output={'scope':'Same preselected 32-molecule pilot; Vina 1.2.7 no_refine, fixed seed104729, CPU1, E1, no max_evals cap. Warm search excludes receptor maps and per-ligand preparation; load_ms recorded separately.','results':results,'roc_auc':auc(labels,energies),'auc_bootstrap_95':np.percentile(samples,[2.5,97.5]).tolist(),'top4_actives':int(labels[np.argsort(energies)[:4]].sum()),'redocking':control}
(OUT/'uncapped_controls.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({'auc':output['roc_auc'],'redocking':control}))
