"""Pinned Vina CLI helpers. A returned score does not attest to search effort."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'tmp' / 'docking-pilot'
EVIDENCE = ROOT / 'docs' / 'evaluation' / 'docking_pilot_2026-09-06'
CASES = [
    ('2P16', 'apixaban', 'factor-Xa'),
    ('4LL3', 'darunavir', 'HIV-protease'),
    ('4TZ4', 'S-Lenalidomide', 'cereblon'),
]


def case_spec(case):
    code, ligand, receptor = case
    params = {}
    for line in (CACHE / 'inputs' / f'{code}_docking_params.txt').read_text().splitlines():
        k, v = line.split(':', 1)
        if k.startswith(('center_', 'size_')):
            params[k] = float(v)
    return dict(id=code, ligand=f'{code}_ligand_{ligand}.pdbqt', receptor=f'{code}_receptor_{receptor}.pdbqt', params=params)


def first_pose(text):
    lines = text.splitlines()
    if 'MODEL 1' in text or any(x.startswith('MODEL') for x in lines):
        start = next(i for i, line in enumerate(lines) if line.startswith('MODEL')) + 1
        end = next(i for i in range(start, len(lines)) if lines[i].startswith('ENDMDL'))
        lines = lines[start:end]
    return '\n'.join(lines) + '\n'


def run_vina(spec, label, *, mode='dock', exhaustiveness=1, max_evals=1000, seed=104729, ligand_path=None, timeout=90):
    work = CACHE / 'runs'
    work.mkdir(exist_ok=True)
    output = work / f'{label}.pdbqt'
    ligand = ligand_path or CACHE / 'inputs' / spec['ligand']
    args = [str(CACHE / 'native' / 'vina_1.2.7_win.exe'), '--receptor', str(CACHE / 'inputs' / spec['receptor']), '--ligand', str(ligand), '--cpu', '1', '--seed', str(seed), '--verbosity', '1']
    for k, v in spec['params'].items():
        args += ['--' + k, str(v)]
    if mode == 'dock':
        args += ['--exhaustiveness', str(exhaustiveness), '--max_evals', str(max_evals), '--num_modes', '1', '--out', str(output)]
    elif mode == 'local':
        args += ['--local_only', '--out', str(output)]
    elif mode == 'score':
        args += ['--score_only']
    else:
        raise ValueError(mode)
    begin = time.perf_counter()
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        wall_ms = (time.perf_counter() - begin) * 1000
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return dict(id=label, case=spec['id'], mode=mode, timeout=True, wall_ms=(time.perf_counter()-begin)*1000)
    (work / f'{label}.stdout.txt').write_text(stdout, encoding='utf-8')
    (work / f'{label}.stderr.txt').write_text(stderr, encoding='utf-8')
    affinity = re.search(r'Estimated Free Energy of Binding\s*:\s*([-+\d.eE]+)', stdout)
    if not affinity:
        affinity = re.search(r'^\s*1\s+([-+\d.eE]+)\s+[-+\d.eE]+\s+[-+\d.eE]+\s*$', stdout, re.M)
    score = float(affinity.group(1)) if affinity else None
    pose = first_pose(output.read_text()) if output.exists() and mode != 'score' else None
    if pose:
        output.write_text(pose, encoding='utf-8')
    return dict(id=label, case=spec['id'], mode=mode, exhaustiveness=exhaustiveness if mode=='dock' else None, max_evals=max_evals if mode=='dock' else None, seed=seed, wall_ms=wall_ms, returncode=code, score=score, pose_path=str(output.relative_to(ROOT)) if pose else None, pose_bytes=len(pose.encode()) if pose else None, stdout_sha256=hashlib.sha256(stdout.encode()).hexdigest())


def save_result(name, obj):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(obj, indent=2) + '\n', encoding='utf-8')
