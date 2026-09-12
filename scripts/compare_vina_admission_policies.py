"""Explicit economic models, not evidence of deployed abuse resistance."""
import json, math
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/evaluation/vina_followup_2026-09-12/admission_policy_comparison.json'
rng = np.random.default_rng(155921)
trials = 200000
rows = []
for p in [.01, .05, .1, .25, 1.]:
    for cap in [1, 5, 20, 100]:
        first = rng.geometric(p, size=trials)
        attempts = np.minimum(first, cap)
        expected_attempts = sum((1-p)**k for k in range(cap))
        for policy, lag in [('immediate_random', 0), ('delayed_provisional', 0),
                            ('deferred_random', 0), ('deferred_random', 2)]:
            immediate = policy != 'deferred_random'
            grants = np.minimum(first-1, cap) if immediate else np.minimum(first+lag, cap)
            exact = (sum((1-p)**k for k in range(1, cap+1)) if immediate else
                     sum((1-p)**max(0, k-lag) for k in range(cap)))
            se = float(grants.std(ddof=1) / math.sqrt(trials))
            assert abs(float(grants.mean())-exact) <= 6*se+1e-10
            # Deferred policy can accept additional outstanding requests before the
            # first verdict. Each submitted result independently enters the audit.
            submitted = expected_attempts if immediate else exact
            rows.append(dict(policy=policy, audit_probability=p, exposure_cap=cap,
                verdict_lag_admissions=lag, zero_work_bad_grants_exact=exact,
                zero_work_bad_grants_mc=float(grants.mean()), mc_standard_error=se,
                expected_submitted_attempts=submitted,
                expected_server_replay_units=p*submitted,
                identity_cost_per_bad_grant=[dict(identity_cost_units=b,
                    cost=b/exact if exact else None) for b in [0, 1, 10, 100]],
                honest_compute_to_replay_ratio=1/p))

bundles = []
for n in [1, 2, 4, 8, 16, 32]:
    for q in [1, 2, 4]:
        if q > n: continue
        for c in range(n+1):
            s = math.comb(c, q)/math.comb(n, q) if c >= q else 0
            bundles.append(dict(n=n, q=q, correct_units=c, pass_probability=s,
                attacker_units_per_success=c/s if s else None,
                honest_units_per_success=n, honest_client_server_ratio=n/q,
                server_units_per_success=q/s if s else None,
                selective_abort_server_units_per_success=q if s else None,
                note='Selective abort assumes attacker knows which committed units are invalid; abandoned challenges still consume identity and issuance limits.'))
            if s: assert c/s >= n-1e-10

fresh = []
for p in [.01, .05, .1, .25, 1.]:
    for f in [0, .1, .25, .5, .75, .9, 1]:
        s = 1-p*(1-f)
        fresh.append(dict(p=p, independently_correct_fraction=f,
            immediate_success_probability=s, work_per_immediate_success=f/s if s else None,
            work_per_deferred_success=f,
            selective_abort_fraction=p*(1-f),
            note='One fresh identity per attempt; no inherited reputation assumed. Deferred access is consumed before auditing.'))

cached_retries=[]
for row in bundles:
    for attempts in [1, 2, 3]:
        p=row['pass_probability']; s=1-(1-p)**attempts
        observed=(rng.binomial(attempts,p,size=trials)>0)
        se=float(observed.std(ddof=1)/math.sqrt(trials))
        assert abs(float(observed.mean())-s)<=6*se+1e-10
        c=row['correct_units']; n=row['n']
        if s: assert c/s>=n/attempts-1e-10
        cached_retries.append(dict(n=n,q=row['q'],correct_units=c,max_challenges=attempts,
            success_before_cap=s,simulated_success=float(observed.mean()),standard_error=se,
            computed_units_per_success=c/s if s else None,
            scope='Same cached partial bundle retried until success or global cap. One credit at most per scientific unit. This weakens the fresh-bundle bound.'))

result = dict(scope='Analytic and Monte Carlo policy models. One unit normalizes molecular compute and warm replay; network, reputation acquisition, queueing and mobile/server hardware asymmetry are separate. No runtime admission policy changed.',
    assumptions=['An audited invalid output is reliably detected.',
        'Random audit is chosen after an immutable commitment and cannot be predicted.',
        'A correct seeded output costs one unit; acceleration/collusion can violate equal-cost accounting.',
        'Finite exposure cap and immediate revocation at the modeled verdict.',
        'Unaudited scientific results remain provisional.'],
    trials=trials, persistent_zero_work=rows, fresh_identity=fresh, bundles=bundles,cached_bundle_retries=cached_retries,
    predictable_periodic=[dict(period=m, adaptive_work_per_admission=1/m,
        server_replay_per_admission=1/m, detection_probability=0,
        strategy='Compute exactly the known audit visits; fabricate the others.') for m in [4, 10, 20, 100]],
    farming=[dict(honest_farming_units=h, post_trust_cap=k,
        zero_work_bad_grants_if_deferred_p05=sum(.95**x for x in range(k)),
        farming_units_per_bad_grant=h/sum(.95**x for x in range(k)))
        for h in [0, 1, 5, 20] for k in [1, 5, 20]],
    recommendation=['Use random immediate audit for a capped trusted one-run tier: unselected requests proceed; selected requests wait for replay. Deferred science validation must not be confused with preventing consumed access.',
        'Delayed provisional access is security-equivalent only if no valuable protected action occurs before a selected verdict. A timer alone adds no work guarantee.',
        'Never advertise random one-run audit as proof that each admitted visitor worked. A fresh zero-cost identity succeeds with probability 1-p without molecular work.',
        'Use unpredictable mandatory q>=1 whole-run audit for risky bundles. Fresh assignments give expected work >=N per success. Up to R retries of cached partial bundles weaken this bound to >=N/R; the existing global per-unit cap is three. N=2 has only a 2:1 honest compute/replay ratio.',
        'Bound outstanding provisional credit, bind identities to the outer layer, quarantine scientific outputs until separately validated, and enforce audit backpressure. These integration requirements are not implemented by this model.'])
OUT.write_text(json.dumps(result, indent=2)+'\n')
print(f'{len(rows)} policy settings and {len(bundles)} bundle attacks checked; wrote {OUT}')
