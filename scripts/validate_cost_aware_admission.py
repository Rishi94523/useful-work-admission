"""Amendment 18: existing cost resampling and actual scheduler sleeper exercise.

No molecular replay or new independent timing observations are claimed here.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from admission_economics_eval import World, attempt

OUT = ROOT / 'local-research/cost-aware-2026-09-29'
PROTOCOL_COMMIT = 'a2d2af1'


def costs(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row['target'], row['id'], row['seed']), []).append(row)
    dev, hold = [], []
    for target in sorted({k[0] for k in groups}):
        keys = sorted((k for k in groups if k[0] == target), key=lambda k: hashlib.sha256(
            ('cost-aware-2026-09-29:' + '/'.join(map(str, k))).encode()).digest())
        n = max(1, len(keys) // 2)
        dev.extend(r for k in keys[:n] for r in groups[k])
        hold.extend(r for k in keys[n:] for r in groups[k])
    predictors = {t: float(np.median([r['wall_ms'] for r in dev if r['target'] == t]))
                  for t in sorted({r['target'] for r in rows})}
    c = np.array([r['wall_ms'] for r in hold]); pred = np.array([predictors[r['target']] for r in hold])
    job_indices = {}
    for i, r in enumerate(hold):
        job_indices.setdefault((r['target'], r['id'], r['seed']), []).append(i)
    results = []
    for seed in range(20260929, 20260934):
        rng = np.random.default_rng(seed)
        for mode in ('mixed_jobs', 'same_job'):
            if mode == 'mixed_jobs': idx = rng.integers(len(hold), size=(10000, 4))
            else:
                jobs = list(job_indices.values())
                idx = np.array([rng.choice(jobs[j], 4, replace=True) for j in rng.integers(len(jobs), size=10000)])
            actual, estimates = c[idx], pred[idx]
            # Random column order makes tied predictions choose randomly.
            selected = {'random': np.zeros(len(idx), dtype=int),
                        'predicted': estimates.argmin(axis=1), 'oracle': actual.argmin(axis=1)}
            for strategy, col in selected.items():
                paid = actual[np.arange(len(idx)), col]
                results.append(dict(seed=seed, bundle=mode, strategy=strategy,
                    expected_cost_ratio=float(4 * paid.mean() / actual.sum(axis=1).mean()),
                    expected_acceptance=.25, useful_units_per_success=1,
                    honest_bundle_ms=float(actual.sum(axis=1).mean())))
            # Rank by public prediction only, never by held-out runtime.
            keep = np.argsort(estimates.mean(axis=1), kind='stable')[:5000]
            for probe_ms in (0, 1, 10):
                selected_cost = actual[keep, selected['predicted'][keep]].sum()
                expected_ms = 4 * (selected_cost + len(idx) * probe_ms) / len(keep)
                results.append(dict(seed=seed, bundle=mode, strategy='predicted_abstain_half',
                    probe_ms=probe_ms, offered_fraction=.5, expected_cost_ratio=float(expected_ms / actual.sum(axis=1).mean()),
                    expected_acceptance_per_submitted=.25, expected_acceptance_per_offer=.125))
    return dict(development_jobs=len({(r['target'], r['id'], r['seed']) for r in dev}),
                heldout_jobs=len(job_indices), development_units=len(dev), heldout_units=len(hold),
                predictor_ms=predictors, rows=results,
                limitations='Existing concurrent timings; resampling with replacement (only three observations per job). Mixed pools are a counterfactual; deployed requests bind one pool. Oracle uses information unavailable before work. No adaptive timing attacker implemented.')


def sleepers(unit_ms):
    results = []
    for policy in ('immediate', 'deferred'):
        for p in (.02, .1, .25):
            with tempfile.TemporaryDirectory(dir=OUT) as work:
                w = World(work, lambda kind: kind == 'honest', policy=policy, audit_probability=p)
                try:
                    for i in range(30):
                        owner = w.identity(); paid = 0
                        for _ in range(3):
                            lease = w.request(owner)
                            if lease.get('status') != 'assigned':
                                w.advance(1800); lease = w.request(owner)
                            assert lease['tier'] == 'bundle', lease
                            outputs = {t['task']: (b'honest:' + t['task'].encode(), 'honest') for t in lease['tasks']}
                            w.advance(4 * unit_ms / 1000 + 4)
                            ok, _ = attempt(w, owner, lease, outputs, lambda *a: True)
                            assert ok
                            paid += 4
                        w.c.grant_trust(owner, allowance=10, ttl=3600)
                        w.advance(600)
                        fraud = requests = audited = 0; before = w.replayed
                        for _ in range(10):
                            lease = w.request(owner)
                            if lease.get('status') != 'assigned': break
                            if lease['tier'] != 'trusted':
                                w.advance(121); break
                            requests += 1; task = lease['tasks'][0]['task']
                            out = {task: b'fabricated:' + task.encode()}
                            root = w.c.output_root(lease['binding'], out)
                            ch = w.c.commit(lease['lease'], owner, lease['binding'], root)
                            r = w.c.submit(lease['lease'], owner, lease['binding'], ch['id'], out)
                            chosen = w.c.audit_targets(lease['lease'])
                            # Redeem before deferred replay to measure irreversible access.
                            if r['status'] == 'granted':
                                w.c.redeem(lease['lease'], owner); fraud += 1
                            if chosen:
                                audited += 1
                                r = w.audit(lease, out, {task: 'fabricated'}, ch)
                                assert r['status'] == 'rejected'
                                break
                            w.advance(4)
                        with w.c.transaction() as db:
                            quarantined = bool(db.execute('SELECT 1 FROM pool_quarantine WHERE owner=?', (owner,)).fetchone())
                        results.append(dict(policy=policy, p=p, identity=i, upfront_units=paid,
                            upfront_ms=paid * unit_ms, fraudulent_admissions=fraud,
                            marginal_molecular_work=0, trusted_requests=requests, failed_audits=audited,
                            lifetime_admissions=3+fraud, quarantined=quarantined,
                            attack_audits=w.replayed-before))
                finally: w.close()
    return results


def main():
    OUT.mkdir(exist_ok=False)
    source = ROOT / 'local-research/trace-attacks-2026-09-29/units.jsonl'
    rows = [json.loads(s) for s in source.read_text().splitlines()]
    control = [r for r in rows if r['variant'] == 'control']
    assert len(control) == 99 and all(r['accepted'] for r in control)
    manifest = dict(protocol_commit=PROTOCOL_COMMIT, runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), audit_draws='OS randomness; retain actual outcomes')
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2))
    cost = costs(control); (OUT/'costs.json').write_text(json.dumps(cost, indent=2))
    sleep = sleepers(float(np.median([r['wall_ms'] for r in control])))
    (OUT/'sleepers.json').write_text(json.dumps(sleep, indent=2))
    summary = {'cost_ratios': {}, 'sleepers': []}
    for mode in ('mixed_jobs', 'same_job'):
        for strategy in ('random','predicted','oracle'):
            xs = [r['expected_cost_ratio'] for r in cost['rows'] if r['bundle']==mode and r['strategy']==strategy]
            summary['cost_ratios'][mode+':'+strategy] = float(np.mean(xs))
    for policy in ('immediate','deferred'):
        for p in (.02,.1,.25):
            rs=[r for r in sleep if r['policy']==policy and r['p']==p]
            summary['sleepers'].append(dict(policy=policy,p=p,identities=len(rs),fraudulent_admissions=sum(r['fraudulent_admissions'] for r in rs),
                upfront_units=sum(r['upfront_units'] for r in rs),max_fraud=max(r['fraudulent_admissions'] for r in rs),
                quarantined=sum(r['quarantined'] for r in rs)))
    summary['HC1'] = summary['cost_ratios']['mixed_jobs:oracle'] < .95
    summary['HC2'] = summary['cost_ratios']['mixed_jobs:predicted'] < .95
    summary['SL1'] = all(r['fraudulent_admissions']<=10 for r in sleep)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))


if __name__ == '__main__': main()
