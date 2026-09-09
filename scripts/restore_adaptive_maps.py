"""Rebuild omitted grids from archived receptors; verify every manifest hash.

Requires the pinned campaign_grid_worker.exe from the earlier docking setup.
Existing mismatching maps are never replaced. Does not redo ligand preparation.
"""
import hashlib,json,subprocess,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CACHE=(ROOT/'tmp/adaptive-docking').resolve()
OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'

def path(relative):
    p=(ROOT/relative).resolve()
    if not p.is_relative_to(CACHE):raise ValueError('Input outside adaptive cache')
    return p

def matches(p,digest):
    return p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==digest

for target in json.loads((OUT/'science_inputs.json').read_text())['targets']:
    if target.get('preparation_failed'):continue
    receptor=path(target['receptor'])
    if not matches(receptor,target['receptor_sha256']):raise ValueError('Restore archived receptor first')
    missing=[]
    for m in target['maps']:
        p=path(m['path'])
        if p.exists() and not matches(p,m['sha256']):raise ValueError('Existing map differs: '+str(p))
        if not p.exists():missing.append(m)
    if missing:
        worker=ROOT/'tmp/docking-audit/campaign_grid_worker.exe'
        if not worker.exists():raise FileNotFoundError('Build the pinned campaign grid worker first')
        CACHE.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='restore-maps-',dir=CACHE) as temporary:
            folder=Path(temporary).resolve()
            if not folder.is_relative_to(CACHE):raise ValueError('Unexpected temporary path')
            subprocess.run([str(worker),str(receptor),*map(str,target['center']),*map(str,target['size']),str(folder/'fa10')],input='QUIT\n',text=True,capture_output=True,timeout=180,check=True)
            for m in target['maps']:
                if Path(m['name']).name!=m['name'] or not matches(folder/m['name'],m['sha256']):raise ValueError('Rebuilt grid differs from the pinned manifest')
            for m in missing:
                destination=path(m['path']);destination.parent.mkdir(parents=True,exist_ok=True)
                with destination.open('xb') as output:output.write((folder/m['name']).read_bytes())
    print(target['target'],len(target['maps']),'grid hashes verified')
