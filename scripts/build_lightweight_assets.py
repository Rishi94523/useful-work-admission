"""Prepare static molecular assets, never candidate energies, for browser search."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.transform import Rotation
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.rigid_grid_search import Grid
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'


def main():
    begin=time.perf_counter();records=json.loads((OUT/'ligands.json').read_text());center=records['box_center']
    assets=BASE/'assets';assets.mkdir(exist_ok=True);maps=BASE/'maps';maps.mkdir(exist_ok=True)
    # 30 A cube keeps all rotated conformers inside the maps (verified below).
    p=subprocess.Popen([str(BASE/'campaign_grid_worker.exe'),str(BASE/'receptor.pdbqt'),*map(str,center),'30','30','30',str(maps/'fa10')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def reply():
        while True:
            line=p.stdout.readline()
            if not line:raise RuntimeError('Native helper closed')
            try:return json.loads(line)
            except json.JSONDecodeError:continue
    ready=reply();print(ready,flush=True);typed=[]
    try:
        for record in records['records']:
            identifier=record['id'];p.stdin.write(f'META "{(BASE / "ligands" / (identifier+".pdbqt")).as_posix()}"\n');p.stdin.flush();meta=reply()
            if 'atoms' not in meta:raise ValueError(f'{identifier}: {meta}')
            conf=np.load(BASE/'ligands'/(identifier+'.conformers.npy'))
            xyz=np.array([a['xyz'] for a in meta['atoms']]);distance=np.linalg.norm(xyz[:,None,:]-conf[0][None,:,:],axis=-1)
            row,col=linear_sum_assignment(distance)
            if len(row)!=len(xyz) or len(xyz)!=conf.shape[1] or distance[row,col].max()>.002:raise ValueError('Heavy atom mapping mismatch')
            conf=conf[:,col,:];conf-=conf.mean(axis=1,keepdims=True)
            if np.linalg.norm(conf,axis=2).max()+1.32>=14.9:raise ValueError('Conformer too large for guaranteed in-box bank')
            typed.append({**record,'atom_types':[a['type'] for a in meta['atoms']], 'conformers_milli':np.floor(conf*1000+.5).astype(int).tolist(),'offset':int(hashlib.sha256(identifier.encode()).hexdigest()[:8],16)})
    finally:p.stdin.write('QUIT\n');p.stdin.flush();p.wait(timeout=15)
    names=sorted(set(t for r in typed for t in r['atom_types']));grids=[Grid(maps/f'fa10.{t}.map') for t in names]
    for r in typed:r['types']=[names.index(t) for t in r['atom_types']]
    packed=np.stack([g.quantized.astype('<i4') for g in grids]);packed.tofile(assets/'maps.bin')
    rotations=np.floor(Rotation.random(128,random_state=104729).as_matrix()*1000000+.5).astype(int)
    meta={'version':'vina-map-fixed-conformer-int8frac-v1','source':'DUD-E FA10; AutoDock Vina 1.2.7 maps; Meeko 0.7.1','map_types':names,'map_shape':list(packed.shape),'map_sha256':hashlib.sha256((assets/'maps.bin').read_bytes()).hexdigest(),'spacing_micro':375000,'origin_micro':np.floor(grids[0].origin*1e6+.5).astype(int).tolist(),'center_milli':np.floor(np.array(center)*1000+.5).astype(int).tolist(),'rotations':rotations.tolist(),'ligands':typed}
    (assets/'assets.json').write_text(json.dumps(meta,separators=(',',':'))+'\n')
    evidence={'map_prepare_ms':ready['map_prepare_ms'],'total_preparation_ms':(time.perf_counter()-begin)*1000,'map_bytes':(assets/'maps.bin').stat().st_size,'metadata_bytes':(assets/'assets.json').stat().st_size,'metadata_sha256':hashlib.sha256((assets/'assets.json').read_bytes()).hexdigest(),'map_sha256':meta['map_sha256'],'receptor_sha256':hashlib.sha256((BASE/'receptor.pdbqt').read_bytes()).hexdigest(),'box_size':[30]*3,'map_types':names,'pose_bank_per_ligand':[len(r['conformers_milli'])*128*512 for r in typed], 'receptor_preparation':'Remove existing hydrogens, fill missing standard element columns, Meeko --read_pdb receptor_heavy.pdb -p. All receptor heavy atoms retained.'}
    (OUT/'assets.json').write_text(json.dumps(evidence,indent=2)+'\n');print(evidence,flush=True)

if __name__=='__main__':main()
