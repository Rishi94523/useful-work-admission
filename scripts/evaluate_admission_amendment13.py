"""Amendment 13: the amendment-12 availability grid with proof-of-work gate
verification (0.77 us per check) in place of a 1.52 s molecular replay.

python scripts/evaluate_admission_amendment13.py --workers 8
Resumes by full cell key. Only the verification time differs from amendment 12.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import evaluate_priority_admission as priority
from scripts.admission_simulation_storage import memory_sqlite

OUT = ROOT / 'local-research/admission-amendment13-2026-09-28'
SEEDS = tuple(range(20260925, 20260930))
PROTOCOL_COMMIT = '4e4f75d'
VERIFY_S = 0.77e-6  # measured native hash-check time per admission


def grid():
    jobs = []
    for seed in SEEDS:
        for m in ('fixed16', 'fixed18'):
            for w in (1, 2, 4, 8):
                for c in (0, .1, .25, 1, 4, 16):
                    jobs.append(('follow', (m, w, c, seed, 'follow')))
        for w in (1, 2, 4, 8):
            for c in (0, .1, .25, 1, 4, 16):
                jobs.append(('patience', ('priority', w, c, seed, 'patience')))
    return jobs


def key(job):
    return json.dumps(job, separators=(',', ':'))


def execute(job):
    kind, item = job
    start = time.perf_counter()
    priority.REPLAY_S = VERIFY_S  # the only change from amendment 12
    with memory_sqlite():
        result = priority.run(item, exact_replay=True)
    result.update(grid=kind, job_key=key(job), verify_s=VERIFY_S, elapsed_s=time.perf_counter()-start)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    paths = ['docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md', 'scripts/evaluate_admission_amendment13.py',
             'scripts/admission_replay_clock.py', 'scripts/admission_simulation_storage.py',
             'scripts/evaluate_priority_admission.py', 'research/ticket_admission.py', 'research/priority_admission.py']
    committed = subprocess.check_output(['git', 'show', PROTOCOL_COMMIT+':'+paths[0]], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') == (ROOT/paths[0]).read_bytes().replace(b'\r\n', b'\n'), 'Protocol not committed'
    manifest = dict(amendment=13, protocol_commit=PROTOCOL_COMMIT, seeds=SEEDS, jobs=len(grid()), verify_s=VERIFY_S,
                    input_tick_s=priority.DT, files={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
                    note='Amendment-12 harness with proof-of-work verification cost; downstream service load not modelled.')
    mp = OUT / 'manifest.json'
    if mp.exists():
        assert json.loads(mp.read_text()) == json.loads(json.dumps(manifest)), 'Immutable manifest changed'
    else:
        mp.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    ledger = OUT / 'results.jsonl'
    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()] if ledger.exists() else []
    done = {r['job_key'] for r in rows}
    todo = [j for j in grid() if key(j) not in done]
    print(f'{len(done)}/{len(grid())} complete; starting {len(todo)}', flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(execute, j) for j in todo]):
            row = future.result()
            with ledger.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(row)+'\n'); fh.flush(); os.fsync(fh.fileno())
            done.add(row['job_key'])
    print('AMENDMENT 13 COMPLETE' if len(done) == len(grid()) else 'CHECKPOINT SAVED', len(done), flush=True)


if __name__ == '__main__':
    main()
