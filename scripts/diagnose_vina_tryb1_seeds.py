"""Frozen old 4+4 TRYB1 inputs; two additional seeds, separate from new panel."""
import gzip, hashlib, json, math
from concurrent.futures import ThreadPoolExecutor, as_completed
from benchmark_vina_task_split import ROOT, OLD, start, stop

OUT = ROOT/'docs/evaluation/vina_followup_2026-09-12/tryb1_old_seed_diagnostic.jsonl'
old = json.loads((ROOT/'docs/evaluation/vina_validation_2026-09-10/matched_ranking.json').read_text())
specs = json.loads((OLD/'converged_inputs.json').read_text())['rows']
target = next(t for t in json.loads((OLD/'science_inputs.json').read_text())['targets'] if t['target']=='tryb1')
rows = [json.loads(x) for x in OUT.read_text().splitlines()] if OUT.exists() else []
done = {(r['id'], r['seed']) for r in rows}

def append(row):
    with OUT.open('a') as f: f.write(json.dumps(row)+'\n'); f.flush()
    print(row['id'], row['seed'], row['normal_score'], row['medium_score'], flush=True)

references = [r for r in old if r['target']=='tryb1']
for r in references:
    spec = next(s for s in specs if s['target']=='tryb1' and s['id']==r['id'])
    assert hashlib.sha256((ROOT/spec['path']).read_bytes()).hexdigest()==spec['sha256']==r['input_sha256']
    if (r['id'],104729) not in done:
        append(dict(target='tryb1',id=r['id'],label=r['label'],seed=104729,
            input_sha256=r['input_sha256'],normal_score=r['normal_score'],medium_score=r['medium_score'],
            normal_evals=r['reference_evals'],medium_evals=r['medium_evals'],
            normal_ms=r['reference_search_ms'],medium_ms=r['medium_search_ms'],
            medium_runs=r['medium_runs'],provenance='Reused rehashed historical paired measurements; no new run.'))

def run(r, seed):
    spec = next(s for s in specs if s['target']=='tryb1' and s['id']==r['id'])
    folder = ROOT/'tmp/vina-followup/old-tryb1'/r['id']/str(seed)
    folder.mkdir(parents=True,exist_ok=True)
    p = start(target, ROOT/spec['path'])
    def execute(n, cap, name):
        directory=folder/name; directory.mkdir(exist_ok=True); pose=folder/(name+'.pdbqt')
        p.stdin.write(f'0 0 {seed} {n} {cap} 9 {directory.as_posix()} {pose.as_posix()}\n'); p.stdin.flush()
        line=p.stdout.readline()
        if not line: raise RuntimeError(p.stderr.read())
        metrics=[json.loads((directory/f'{i}.task.json').read_text()) for i in range(n)]
        return json.loads(line),metrics,pose.read_text()
    try:
        normal,nm,np=execute(8,0,'normal'); budget=sum(m['evals'] for m in nm)
        n=math.ceil(budget/256000); assert n<=512
        medium,mm,mp=execute(n,256000,'medium')
        return dict(target='tryb1',id=r['id'],label=r['label'],seed=seed,input_sha256=spec['sha256'],
            normal_score=normal['score'],medium_score=medium['score'],normal_evals=budget,
            medium_evals=sum(m['evals'] for m in mm),normal_ms=sum(m['ms'] for m in nm),
            medium_ms=sum(m['ms'] for m in mm),medium_runs=n,normal_pose=np,medium_pose=mp,
            provenance='New paired run on frozen old MMFF inputs; two workers alongside larger campaign.')
    finally: stop(p)

with ThreadPoolExecutor(max_workers=2) as pool:
    futures=[pool.submit(run,r,seed) for r in references for seed in [130363,155921] if (r['id'],seed) not in done]
    for future in as_completed(futures): append(future.result())
