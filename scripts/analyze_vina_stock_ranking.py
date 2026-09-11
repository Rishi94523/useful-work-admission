"""Recheck full existing stock panels and their input hashes; do not rerun history."""
import hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10'
raw=OLD/'stock_converged_all.jsonl';rows=[json.loads(x) for x in raw.read_text().splitlines()];inputs=json.loads((OLD/'converged_inputs.json').read_text())['rows'];rng=np.random.default_rng(104729);results=[]
for target in ['fa10','hs90a','tryb1']:
 rs=[r for r in rows if r['target']==target and r['id']!='crystal'];assert len(rs)==16
 for r in rs:
  spec=next(i for i in inputs if i['target']==target and i['id']==r['id']);assert hashlib.sha256((ROOT/spec['path']).read_bytes()).hexdigest()==r['input_sha256']==spec['sha256']
 active=np.array([r['score'] for r in rs if r['label']=='active' and r['ok']]);decoy=np.array([r['score'] for r in rs if r['label']=='decoy' and r['ok']]);known=float(((active[:,None]<decoy)+.5*(active[:,None]==decoy)).sum());missing=64-len(active)*len(decoy)
 bootstrap=[]
 if not missing:
  for _ in range(10000):
   a=rng.choice(active,8);d=rng.choice(decoy,8);bootstrap.append(float(((a[:,None]<d)+.5*(a[:,None]==d)).mean()))
 results.append({'target':target,'known_active':len(active),'known_decoy':len(decoy),'auc':known/64 if not missing else None,'missing_outcome_auc_bounds':[known/64,(known+missing)/64],'bootstrap95':np.percentile(bootstrap,[2.5,97.5]).tolist() if bootstrap else None,'missing_ids':[r['id'] for r in rs if not r['ok']],'input_hashes_verified':True})
OUT.mkdir(exist_ok=True)
(OUT/'stock_ranking_reanalysis.json').write_text(json.dumps({'scope':'Reanalysis of earlier measured stock E8 runs, not new timings. Full preselected8-active/8-decoy panels. Inputs rehashed now. 16 compounds per target remain an underpowered pilot; no target exclusion or missing-run deletion.','source_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'source_path':raw.relative_to(ROOT).as_posix(),'targets':results},indent=2)+'\n')
print(results)
