"""Run the immutable amendment-12 grids without overwriting legacy evidence.

python scripts/evaluate_admission_amendment12.py --workers 8
Interrupted runs resume by full cell key, including seed. Only this launcher
selects exact replay timing; the historical runners retain their legacy mode.
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
from scripts import evaluate_attested_admission as attested
from scripts.admission_simulation_storage import memory_sqlite

OUT = ROOT / 'local-research/admission-amendment12-2026-09-25/memory-sqlite'
SEEDS = tuple(range(20260925, 20260930))
PROTOCOL_COMMIT = 'a730797'


def grid():
    jobs = []
    for seed in SEEDS:
        for strategy in ('follow', 'patience'):
            mechanisms = ('fixed16', 'fixed18', 'priority') if strategy == 'follow' else ('priority',)
            for m in mechanisms:
                for w in (1, 2, 4, 8):
                    for c in (0, .1, .25, 1, 4, 16):
                        jobs.append((strategy, (m, w, c, seed, strategy)))
        for exp in ('oneshot', 'bootstrap'):
            for item in attested.grid(exp):
                jobs.append((exp, (*item[:-1], seed)))
    return jobs


def key(job):
    return json.dumps(job, separators=(',', ':'))


def execute(job):
    kind, item = job
    start = time.perf_counter()
    fn = priority.run if kind in ('follow', 'patience') else attested.run
    with memory_sqlite():
        result = fn(item, exact_replay=True)
    result.update(grid=kind, job_key=key(job), elapsed_s=time.perf_counter()-start)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--limit', type=int, help='Run only the first N pending cells; resume without this option')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('workers must be positive')
    OUT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'tmp').mkdir(exist_ok=True)
    paths = ['docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md',
             'scripts/evaluate_admission_amendment12.py', 'scripts/admission_replay_clock.py',
             'scripts/admission_simulation_storage.py',
             'scripts/evaluate_priority_admission.py', 'scripts/evaluate_attested_admission.py',
             'research/ticket_admission.py', 'research/priority_admission.py', 'research/attested_admission.py']
    manifest = dict(amendment=12, protocol_commit=PROTOCOL_COMMIT, seeds=SEEDS,
                    jobs=len(grid()), replay_s=priority.REPLAY_S, input_tick_s=priority.DT,
                    files={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
                    storage='Private in-memory SQLite, identical SQL and transaction boundaries; not a throughput benchmark',
                    note='Exact replay service; input polling and expected attacker puzzle costs remain modeled.')
    # Verify the protocol really was committed, not merely written before launch.
    committed = subprocess.check_output(['git','show',PROTOCOL_COMMIT+':'+paths[0]], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') == (ROOT/paths[0]).read_bytes().replace(b'\r\n', b'\n')
    mp = OUT / 'manifest.json'
    encoded = json.dumps(manifest, indent=2)
    if mp.exists():
        assert json.loads(mp.read_text()) == json.loads(encoded), 'Immutable manifest changed'
    else:
        mp.write_text(encoded, encoding='utf-8')
    ledger = OUT / 'results.jsonl'
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()] if ledger.exists() else []
    done = {r['job_key'] for r in rows}
    assert len(done) == len(rows), 'Duplicate cell in ledger'
    todo = [job for job in grid() if key(job) not in done]
    if args.limit is not None:
        todo = todo[:args.limit]
    print(f'{len(done)}/{len(grid())} complete; starting {len(todo)} with {args.workers} processes', flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(execute, job):job for job in todo}
        for future in as_completed(futures):
            row = future.result()
            with ledger.open('a', encoding='utf-8') as fh:
                fh.write(json.dumps(row)+'\n'); fh.flush(); os.fsync(fh.fileno())
            done.add(row['job_key'])
            print(f"{len(done)}/{len(grid())} {row['job_key']} {row['elapsed_s']:.1f}s", flush=True)
    print('AMENDMENT 12 COMPLETE' if len(done)==len(grid()) else 'CHECKPOINT SAVED', flush=True)


if __name__ == '__main__':
    main()
