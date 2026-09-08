import hashlib,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.lightweight_docking import Assets
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07';a=Assets(BASE/'assets');results=[]
for identifier in [a.meta['ligands'][i]['id'] for i in [0,7,16,23]]:
    t=time.perf_counter();xyz=a.positions(identifier,np.arange(8192,16384));atoms=xyz.shape[1]
    pose_hashes=[hashlib.sha256(p.astype('<i4').tobytes()).digest() for p in xyz]
    previous=set(pose_hashes[:4096]);new=pose_hashes[4096:]
    delta=xyz*1000-a.origin;cell=delta//a.spacing;fraction=((delta%a.spacing)*256+a.spacing//2)//a.spacing
    types=np.broadcast_to(np.array(a.ligands[identifier]['types'])[None,:,None],(len(xyz),atoms,1))
    keys=np.concatenate([types,cell,fraction],axis=-1).astype('<i2');previous_keys={row.tobytes() for row in keys[:4096].reshape(-1,7)}
    new_keys=[row.tobytes() for row in keys[4096:].reshape(-1,7)]
    results.append({'id':identifier,'previous_poses':4096,'new_poses':4096,'exact_pose_cache_hits':sum(h in previous for h in new),'unique_new_pose_coordinates':len(set(new)),'new_atom_queries':len(new_keys),'queries_reusable_from_previous_range':sum(k in previous_keys for k in new_keys),'unique_new_atom_queries':len(set(new_keys)),'analysis_ms':(time.perf_counter()-t)*1000})
(OUT/'cache.json').write_text(json.dumps({'scope':'Two adjacent disjoint ranges per four ligands; exact quantized poses and per-atom interpolation tuples. These cache hit rates do not bound all algorithms or cross-campaign caches.','results':results},indent=2)+'\n')
print(json.dumps(results))
