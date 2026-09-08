"""Download public DUD-E inputs into an isolated research cache."""
import hashlib
import json
from pathlib import Path
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'
BASE.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
records=[]
for name in ['actives_final.sdf.gz','decoys_final.sdf.gz','crystal_ligand.mol2','receptor.pdb']:
    url='https://dude.docking.org/targets/fa10/'+name;dest=BASE/name
    begin=time.perf_counter()
    if not dest.exists():
        with urllib.request.urlopen(url,timeout=120) as response:
            data=response.read(120_000_001)
        if len(data)>120_000_000:raise RuntimeError('Download exceeds research cap')
        dest.write_bytes(data)
    data=dest.read_bytes();records.append({'url':url,'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'download_or_cached_read_s':time.perf_counter()-begin})
    print(name,len(data),flush=True)
(OUT/'sources.json').write_text(json.dumps({'dataset':'DUD-E FA10; published benchmark, not prospective discovery','citation':'Mysinger et al., J. Med. Chem. 2012, doi:10.1021/jm300687e','files':records,'dependencies':{'rdkit':'2025.9.6','meeko':'0.7.1','gemmi':'0.7.5'}},indent=2)+'\n')
