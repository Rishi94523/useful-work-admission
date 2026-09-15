"""GPU score-only diagnostic on unchanged stock poses; separate durable ledger."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from scipy.optimize import linear_sum_assignment
from run_stock_diagnostic import metrics, auc

OUT = ROOT/'local-research/gnina-diagnostic'
EXE = ROOT/'tmp/gnina/gnina.cuda12.8.static'
PROTOCOL = ROOT/'benchmarks/gnina_rescoring_diagnostic.json'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''): h.update(block)
    return h.hexdigest()


def linux(path):
    p = Path(path).resolve().as_posix()
    return '/mnt/'+p[0].lower()+p[2:]


def poses(text):
    return [part+'ENDMDL\n' for part in text.split('ENDMDL') if 'ATOM' in part]


def geometry_error(source, mol):
    atoms = [l for l in source.splitlines() if l.startswith(('ATOM', 'HETATM')) and l[77:].strip() not in ('H', 'HD', 'HS')]
    elements = {'A':'C', 'NA':'N', 'NS':'N', 'OA':'O', 'OS':'O', 'SA':'S'}
    types = [elements.get(l[77:].strip(), l[77:].strip()) for l in atoms]
    xyz = np.array([[float(l[i:i+8]) for i in (30,38,46)] for l in atoms])
    heavy = [a for a in mol.GetAtoms() if a.GetAtomicNum()>1]
    assert len(heavy)==len(atoms), 'Heavy atom count changed'
    target = mol.GetConformer().GetPositions()[[a.GetIdx() for a in heavy]]
    cost = np.linalg.norm(xyz[:,None]-target[None], axis=-1)
    for i, symbol in enumerate(types):
        for j, atom in enumerate(heavy):
            if atom.GetSymbol().lower()!=symbol.lower(): cost[i,j] += 1000
    i,j = linear_sum_assignment(cost)
    return float(cost[i,j].max())


def validation_molecule(text):
    """Coordinate/element container only; never used as scientific input."""
    lines=[l for l in text.splitlines() if l.startswith(('ATOM','HETATM')) and l[77:].strip() not in ('H','HD','HS')]
    elements={'A':'C','NA':'N','NS':'N','OA':'O','OS':'O','SA':'S'}
    mol=Chem.RWMol();conf=Chem.Conformer(len(lines))
    for i,line in enumerate(lines):
        kind=line[77:].strip();mol.AddAtom(Chem.Atom(elements.get(kind,kind)));conf.SetAtomPosition(i,tuple(float(line[j:j+8]) for j in (30,38,46)))
    mol.AddConformer(conf);return mol.GetMol()


def source_jobs():
    jobs = []
    old = ROOT/'local-research/ranking-extension-2026-09-14'
    inputs = {t['target']:t for t in json.loads((old/'large_inputs.json').read_text())['targets']}
    for row in map(json.loads, (old/'large_stock.jsonl').read_text().splitlines()):
        if not row['ok']: continue
        t = inputs[row['target']]
        jobs.append({'dataset':'negative_extension', 'target':row['target'], 'id':row['id'], 'compound_id':row['id'], 'label':row['label'], 'required_states':1, 'vina_score':row['score'], 'pose_text':row['pose'], 'receptor':str(ROOT/t['receptor']), 'receptor_sha256':t['receptor_sha256']})
    base = ROOT/'local-research/published-vina-validation-2026-09-15'
    inputs = {t['target']:t for t in json.loads((base/'inputs.json').read_text())['targets']}
    # Ignore an in-flight final append; complete lines must always parse.
    ledger_text=(base/'stock_jobs.jsonl').read_text()
    for row in map(json.loads, ledger_text[:ledger_text.rfind('\n')+1].splitlines()):
        if not row['ok'] or row['label']=='crystal': continue
        t = inputs[row['target']];p = ROOT/row['pose_path'];assert sha(p)==row['pose_sha256']
        compound = next(c for c in t['compounds'] if c['id']==row['compound_id'])
        jobs.append({'dataset':'published', 'target':row['target'], 'id':row['id'], 'compound_id':row['compound_id'], 'label':row['label'], 'required_states':compound['states'], 'vina_score':row['score'], 'pose_text':p.read_text(), 'receptor':str(ROOT/t['receptor']), 'receptor_sha256':t['receptor_sha256']})
    return jobs


def score(job):
    folder = OUT/job['dataset']/job['target']/job['id'];folder.mkdir(parents=True, exist_ok=True)
    inp = folder/'original.pdbqt';inp.write_text(job['pose_text']);original_sha = sha(inp)
    assert sha(job['receptor'])==job['receptor_sha256']
    # Native PDBQT output avoids GNINA's OpenBabel conversion path entirely.
    dest = folder/'rescored.pdbqt'
    libraries = ':'.join(linux(p) for p in sorted((ROOT/'tmp/gnina/cuda-libs/nvidia').glob('*/lib')))+':/usr/lib/wsl/lib'
    # GNINA's native PDBQT parser rejects multi-MODEL input. Supply each
    # unchanged pose as its own ligand; strip MODEL/ENDMDL and empty/NUL-only
    # padding lines, retaining every atom record and the original source file.
    before = poses(job['pose_text']);ligand_args=[]
    for index, pose in enumerate(before):
        single=folder/f'pose_{index:03d}.pdbqt'
        single.write_text('\n'.join(line for line in pose.splitlines() if line.strip('\x00 \t\r\n') and not line.startswith(('MODEL','ENDMDL')))+'\n')
        ligand_args += ['-l',linux(single)]
    args = ['wsl','-d','Ubuntu-22.04','-u','root','--','env','LD_LIBRARY_PATH='+libraries,'/usr/bin/time','-f','%e %U %S %M','-o',linux(folder/'resources.txt'),linux(EXE),'-r',linux(job['receptor']),*ligand_args,'-o',linux(dest)] + json.loads(PROTOCOL.read_text())['flags']
    samples = [];stop = threading.Event()
    def monitor():
        while not stop.is_set():
            sample = subprocess.run(['nvidia-smi','--query-gpu=utilization.gpu,memory.used,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True)
            try: samples.append([float(v.strip()) for v in sample.stdout.strip().split(',')])
            except ValueError: pass
            stop.wait(.5)
    watcher = threading.Thread(target=monitor,daemon=True);watcher.start()
    begin = time.perf_counter()
    try: run = subprocess.run(args, capture_output=True, text=True, timeout=900)
    finally: stop.set();watcher.join(timeout=5)
    wall = time.perf_counter()-begin
    (folder/'gnina.log').write_text(run.stdout+run.stderr)
    assert run.returncode==0, 'GNINA failed: '+run.stderr[-500:]
    assert 'No GPU detected' not in run.stdout+run.stderr, 'GPU fallback detected'
    after = poses(dest.read_text())
    assert len(after)==len(before), 'GNINA pose count changed'
    scores = []
    for source, output in zip(before, after):
        error = geometry_error(source, validation_molecule(output));assert error<=.002, 'Pose moved or output order changed'
        affinity=float(re.search(r'REMARK CNNaffinity\s+([-\d.eE+]+)',output).group(1));cnnscore=float(re.search(r'REMARK CNNscore\s+([-\d.eE+]+)',output).group(1))
        assert np.isfinite([affinity,cnnscore]).all(),'Nonfinite CNN output'
        scores.append({'CNNaffinity':affinity, 'CNNscore':cnnscore, 'maximum_coordinate_error_A':error})
    assert sha(inp)==original_sha and sha(job['receptor'])==job['receptor_sha256']
    return {k:v for k,v in job.items() if k!='pose_text'} | {'ok':True, 'poses':scores, 'wall_seconds':wall, 'pose_sha256':original_sha, 'output_sha256':sha(dest), 'command':args, 'resources':(folder/'resources.txt').read_text(), 'gpu_samples_utilization_percent_total_memory_MiB_power_W':samples, 'telemetry_caveat':'Total device samples include desktop and other processes; wall time includes startup and monitor shutdown, not isolated GPU kernel time.'}


def report(rows):
    summaries = []
    for dataset,target in sorted({(r['dataset'],r['target']) for r in rows}):
        group = [r for r in rows if r['dataset']==dataset and r['target']==target]
        compounds = []
        for cid in sorted({r['compound_id'] for r in group}):
            states = [r for r in group if r['compound_id']==cid]
            if len(states)!=states[0]['required_states'] or not all(r['ok'] for r in states): continue
            best = min(states, key=lambda r:(r['vina_score'],r['id']))
            compounds.append({'label':best['label'], 'vina':best['vina_score'], 'affinity':-best['poses'][0]['CNNaffinity'], 'cnnscore':-best['poses'][0]['CNNscore'], 'pool_affinity':-max(p['CNNaffinity'] for r in states for p in r['poses']), 'seconds':sum(r['wall_seconds'] for r in states)})
        item = {'dataset':dataset, 'target':target, 'complete_compounds':len(compounds), 'full_panel':len(compounds)==96, 'scoring_failures':sum(not r['ok'] for r in group)}
        if compounds:
            item['seconds_per_compound_mean'] = float(np.mean([r['seconds'] for r in compounds]))
            item['metrics'] = {method:metrics([{'ok':True, 'label':r['label'], 'score':r[method]} for r in compounds],5000) for method in ('vina','affinity','cnnscore','pool_affinity')}
            act = [i for i,r in enumerate(compounds) if r['label']=='active'];dec = [i for i,r in enumerate(compounds) if r['label']=='decoy']
            if act and dec:
                rng = np.random.default_rng(104729);delta = []
                for _ in range(5000):
                    a = rng.choice(act,len(act));d = rng.choice(dec,len(dec))
                    delta.append(auc([compounds[i]['affinity'] for i in a],[compounds[i]['affinity'] for i in d])-auc([compounds[i]['vina'] for i in a],[compounds[i]['vina'] for i in d]))
                item['fixed_pose_affinity_delta_auc_95'] = np.percentile(delta,[2.5,97.5]).tolist()
        summaries.append(item)
    (OUT/'summary.json').write_text(json.dumps(summaries, indent=2))


def main():
    parser = argparse.ArgumentParser();parser.add_argument('--once', action='store_true');args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    while True:
        progress = ROOT/'local-research/vina-concurrency/progress.json'
        if progress.exists() and json.loads(progress.read_text()).get('phase')=='campaign_resumed': break
        time.sleep(30)
    metadata = {'protocol_sha256':sha(PROTOCOL), 'binary_sha256':sha(EXE), 'script_sha256':sha(Path(__file__)), 'version':'1.3.3', 'negative_ledger_sha256':sha(ROOT/'local-research/ranking-extension-2026-09-14/large_stock.jsonl'), 'negative_inputs_sha256':sha(ROOT/'local-research/ranking-extension-2026-09-14/large_inputs.json'), 'published_inputs_sha256':sha(ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json')}
    metadata['cuda_runtime_packages'] = {d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(ROOT/'tmp/gnina/cuda-libs')])}
    release = json.loads((ROOT/'tmp/gnina/release.json').read_text(encoding='utf-8-sig'))
    assert 'sha256:'+metadata['binary_sha256']==release['assets'][0]['digest'], 'Official binary digest mismatch'
    manifest = OUT/'execution_manifest.json'
    if manifest.exists(): assert json.loads(manifest.read_text())==metadata
    else: manifest.write_text(json.dumps(metadata, indent=2))
    ledger = OUT/'scores.jsonl';rows = list(map(json.loads,ledger.read_text().splitlines())) if ledger.exists() else []
    key = lambda r:(r['dataset'],r['target'],r['id'])
    done = {key(r) for r in rows}
    while True:
        changed=False
        for job in source_jobs():
            if key(job) in done: continue
            try: result = score(job)
            except Exception as error: result = {k:v for k,v in job.items() if k!='pose_text'} | {'ok':False, 'error':str(error)}
            with ledger.open('a') as stream: stream.write(json.dumps(result)+'\n');stream.flush();os.fsync(stream.fileno())
            rows.append(result);done.add(key(result));changed=True;print(key(result),result['ok'],result.get('error',''),flush=True)
            (OUT/'progress.json').write_text(json.dumps({'saved_states':len(rows),'failures':sum(not r['ok'] for r in rows),'latest':key(result),'updated':time.time()},indent=2))
            if len(rows)%32==0: report(rows)
            if sum(not r['ok'] for r in rows[-3:])==3: raise RuntimeError('Three consecutive failures; inspect before continuing')
        if changed: report(rows)
        if args.once or json.loads((ROOT/'local-research/published-vina-validation-2026-09-15/progress.json').read_text()).get('complete'): break
        time.sleep(30)


if __name__ == '__main__': main()
