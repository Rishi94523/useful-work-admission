"""Isolated capacity counterexamples and baseline audit; never changes deployment.

Uses real PoolAdmission transactions, fixture outputs and explicit replay verdicts.
It is NOT an HTTP load test or a molecular benchmark. Queue variants are
counterfactual research adapters, not proposed production implementations.
All output goes to a new, ignored evidence directory; existing evidence is read only.
"""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.pool_admission import PoolAdmission


class SeparateCapacity(PoolAdmission):
    """Serial experiment only: 16 submitted/committed + 256 total leases.

    Keep the original lease, credit, seed and audit machinery. Merely admitting
    more idle clients must not be mistaken for a stateless allocation design.
    """
    def request(self, pool, identity):
        with self.transaction() as db:
            self._expire(db, self.clock())
            rows = db.execute("SELECT p.state FROM pool_policy p JOIN leases l "
                              "ON l.id=p.lease WHERE l.status IN ('OPEN','COMMITTED') "
                              "OR p.state='DEFERRED'").fetchall()
            idle = sum(r['state'] == 'OPEN' for r in rows)
            if len(rows) >= 256:
                return {'status': 'assignment_capacity'}
            before = self.capacity
            try:
                self.capacity = idle + 16
                return super().request(pool, identity)
            finally:
                self.capacity = before


def world(path, cls=PoolAdmission, **kwargs):
    now = [0.0]
    c = cls(path, clock=lambda: now[0], **kwargs)
    spec = dict(model_version='capacity-fixture', receptor='r', ligand='l',
                conformer_bank='i', region='b', search_parameters={'max_evals':256000})
    for i in range(2):
        c.register_pool('p'+str(i), spec, list(range(i*1024, (i+1)*1024)))
    return c, now


def submit(c, lease, owner):
    outputs = {t['task']: b'capacity-fixture-not-molecular-output' for t in lease['tasks']}
    challenge = c.commit(lease['lease'], owner, lease['binding'], c.output_root(lease['binding'], outputs))
    r = c.submit(lease['lease'], owner, lease['binding'], challenge['id'], outputs)
    return r, outputs


def capacity_case(path, cls, holders, upload=False):
    c, now = world(path, cls)
    accepted = 0
    for i in range(holders):
        now[0] = i / 10
        # Deliberately isolate the lease cap from the rate cap in this case.
        with c.transaction() as db:
            db.execute('UPDATE admission_budget SET tokens=32,updated=?', (now[0],))
        l = c.request('p0', 'holder-'+str(i))
        if l['status'] != 'assigned':
            break
        accepted += 1
        if upload:
            submit(c, l, 'holder-'+str(i))
    now[0] += 1
    with c.transaction() as db:
        db.execute('UPDATE admission_budget SET tokens=32,updated=?', (now[0],))
    start = time.perf_counter()
    honest = c.request('p1', 'honest')
    result = dict(variant=cls.__name__, holders=holders, allocated=accepted,
                  attack='fabricated_upload_without_replay' if upload else 'idle',
                  honest_status=honest['status'], request_ms=(time.perf_counter()-start)*1000)
    if honest['status'] == 'assigned':
        _, outputs = submit(c, honest, 'honest')
        verdict = {t:(hashlib.sha256(outputs[t]).hexdigest(), True)
                   for t in c.audit_targets(honest['lease'])}
        result['fixture_replay_status'] = c.replay(honest['lease'], verdict)['status']
        c.redeem(honest['lease'], 'honest')
    return result


def refill_case(path, corrected=False):
    c, now = world(path, capacity=256)
    with c.transaction() as db:
        db.execute('UPDATE admission_budget SET tokens=0,updated=0')
    counts = Counter()
    for i in range(1,101):
        now[0] = i/10
        with c.transaction() as db:
            b = db.execute('SELECT * FROM admission_budget').fetchone()
            tokens = min(c.global_burst, b['tokens']+(now[0]-b['updated'])*c.global_rate)
        r = c.request('p0', 'fresh-'+str(i)); counts[r['status']] += 1
        if tokens < 1:
            # Explicitly replay both accounting rules even after the core fix.
            with c.transaction() as db:
                db.execute('UPDATE admission_budget SET tokens=?,updated=?', (tokens if corrected else 0,now[0]))
    return dict(corrected_counterfactual=corrected, seconds=10, requests=100,
                legacy_discard_emulated=not corrected,
                configured_tokens_per_second=2, outcomes=dict(counts))


def devices():
    result=[]
    for p in sorted((ROOT/'local-research/device-timing').glob('*.json')):
        r=json.loads(p.read_text()); warm=[u['run_ms'] for u in r['units']
            if u['mode']=='reuse' and not u.get('overlaps_hidden',False)]
        puzzles=[u['ms'] for u in r['puzzles'] if not u.get('overlaps_hidden',False)]
        def stats(x):
            return dict(n=len(x),median_ms=statistics.median(x),p95_ms=float(np.percentile(x,95)),max_ms=max(x))
        result.append(dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            device=r['device_model'],visibility_instrumented='visibility' in r,
            hidden_events=r.get('hidden_events'),warm=stats(warm),puzzles=stats(puzzles),
            cold_first_callback_ms=r['units'][0]['at_ms'],server_checks=r.get('server_checks'),
            unique_unit_indices=len({u['index'] for u in r['units']})))
    return result


def puzzle_projection():
    # Sum of independent geometric solve counts, fixed expected total work.
    # Not device measurements; geometric distribution assumes independent hashes.
    rng=np.random.default_rng(20260924); rows=[]
    for k in (1,4,16,64):
        x=rng.geometric(k/1048576,size=(100000,k)).sum(axis=1)/1048576
        median=float(np.median(x))
        rows.append(dict(subpuzzles=k,expected_total_hashes=1048576,
            verifier_hashes=k,median_over_expected=median,
            p95_over_median=float(np.percentile(x,95))/median,
            p99_over_median=float(np.percentile(x,99))/median,
            over_twice_median=float(np.mean(x>2*median))))
    return rows


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    out=(ROOT/args.out).resolve()
    if not out.is_relative_to(ROOT/'local-research'):
        raise ValueError('Evidence must be under local-research')
    out.mkdir(parents=True,exist_ok=False)
    manifest={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scheduler_sha256':hashlib.sha256((ROOT/'research/pool_admission.py').read_bytes()).hexdigest(),
        'pre_execution_design': 'Real scheduler fixtures: idle 16/256; fake pending 16; fractional refill; device reanalysis; geometric subpuzzle projection. No production changes.',
        'limits':'Fixture verdicts are assumed. No actual molecular replay, network load, or new phone measurements.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    start=time.perf_counter();cases=[]
    with tempfile.TemporaryDirectory(dir=out) as d:
        for n,(cls,holders,upload) in enumerate([(PoolAdmission,16,False),
                (SeparateCapacity,16,False),(SeparateCapacity,256,False),
                (PoolAdmission,16,True),(SeparateCapacity,16,True)]):
            cases.append(capacity_case(Path(d)/f'capacity{n}.sqlite',cls,holders,upload))
        refill=[refill_case(Path(d)/f'refill{n}.sqlite',bool(n)) for n in range(2)]
    r={'capacity_cases':cases,'refill_cases':refill,'device_reanalysis':devices(),
       'simulated_subpuzzles':puzzle_projection(),'elapsed_seconds':time.perf_counter()-start}
    (out/'results.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='device_reanalysis'},indent=2))


if __name__=='__main__':main()
