"""Amendment 14 availability: the amendment-13 grid (fixed 16-bit and 18-bit
puzzles and the full-patience priority queue; 1-8 workers; 0-16 attacker
cores; five seeds) with each inference model's measured verification time at
an 8% audit rate in place of the 1.52 s docking replay.

python scripts/evaluate_admission_amendment14.py --workers 8
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import evaluate_priority_admission as priority
from scripts.admission_simulation_storage import memory_sqlite

LEVERAGE = ROOT / 'local-research/inference-leverage-2026-09-28/results.json'
OUT = ROOT / 'local-research/admission-amendment14-2026-09-28'
SEEDS = tuple(range(20260925, 20260930))


def verify_times():
    return {r['model']: r['verify_eff_ms'] / 1000 for r in json.loads(LEVERAGE.read_text(encoding='utf-8'))}


def grid():
    jobs = []
    for model, verify_s in sorted(verify_times().items()):
        for seed in SEEDS:
            for m in ('fixed16', 'fixed18'):
                for w in (1, 2, 4, 8):
                    for c in (0, .1, .25, 1, 4, 16):
                        jobs.append((model, verify_s, 'follow', (m, w, c, seed, 'follow')))
            for w in (1, 2, 4, 8):
                for c in (0, .1, .25, 1, 4, 16):
                    jobs.append((model, verify_s, 'patience', ('priority', w, c, seed, 'patience')))
    return jobs


def key(job): return json.dumps([job[0], job[2], job[3]], separators=(',', ':'))


def execute(job):
    model, verify_s, kind, item = job
    start = time.perf_counter(); priority.REPLAY_S = verify_s
    with memory_sqlite():
        result = priority.run(item, exact_replay=True)
    result.update(workload=model, verify_s=verify_s, grid=kind, job_key=key(job), elapsed_s=time.perf_counter() - start)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--workers', type=int, default=8); args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    paths = ['scripts/evaluate_admission_amendment14.py', 'scripts/admission_replay_clock.py', 'scripts/admission_simulation_storage.py',
             'scripts/evaluate_priority_admission.py', 'research/ticket_admission.py', 'research/priority_admission.py']
    manifest = dict(amendment=14, seeds=SEEDS, jobs=len(grid()), verify_s=verify_times(),
                    leverage_sha256=hashlib.sha256(LEVERAGE.read_bytes()).hexdigest(),
                    files={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths})
    mp = OUT / 'manifest.json'
    if mp.exists(): assert json.loads(mp.read_text()) == json.loads(json.dumps(manifest)), 'Immutable manifest changed'
    else: mp.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    ledger = OUT / 'results.jsonl'
    done = {json.loads(l)['job_key'] for l in ledger.read_text().splitlines() if l.strip()} if ledger.exists() else set()
    todo = [j for j in grid() if key(j) not in done]; print(f'{len(done)}/{len(grid())} complete; starting {len(todo)}', flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(execute, j) for j in todo]):
            row = future.result()
            with ledger.open('a', encoding='utf-8') as fh: fh.write(json.dumps(row) + '\n'); fh.flush(); os.fsync(fh.fileno())
            done.add(row['job_key'])
    print('AMENDMENT 14 AVAILABILITY COMPLETE' if len(done) == len(grid()) else 'CHECKPOINT SAVED', len(done), flush=True)


if __name__ == '__main__': main()
