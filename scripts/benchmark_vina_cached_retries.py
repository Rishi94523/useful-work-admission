"""Real SQLite/challenge transitions, modeled replay verdicts; no docking timing."""
import hashlib, json, math, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from research.vina_pool_campaign import VinaPoolCampaign

TRIALS=1000
clock=[0.]
with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
    campaign=VinaPoolCampaign(Path(folder)/'retries.sqlite',clock=lambda:clock[0])
    successes=attempts=abandoned=0
    begin=time.perf_counter()
    for trial in range(TRIALS):
        spec=dict(model_version='scheduler-fixture',receptor='fixture',ligand=str(trial),
            conformer_bank='fixture-'+str(trial),region='fixture',search_parameters={'max_evals':256000})
        pool='pool-'+str(trial); campaign.register_pool(pool,spec,[1,2,3,4])
        accepted=False
        for attempt in range(3):
            owner=f'fresh-{trial}-{attempt}'
            lease=campaign.lease(pool,owner,jobs=4,ttl=1)
            # First ordinal is the only modeled correctly computed unit. Client
            # sees the challenge only after commitment, and abandons bad draws.
            ids=[r['task'] for r in lease['tasks']]
            outputs={task:(b'correct-fixture' if i==0 else b'invalid-fixture') for i,task in enumerate(ids)}
            commitment=hashlib.sha256(b''.join(outputs.values())).hexdigest()
            ch=campaign.commit(lease['lease'],owner,lease['binding'],commitment,samples=1)
            attempts+=1
            good=all(j==0 for j,_ in ch['draws'])
            if good:
                campaign.finish_outputs(lease['lease'],owner,lease['binding'],ch['id'],commitment,outputs,[ids[0]])
                successes+=1;accepted=True
                assert campaign.coverage(pool)['completed']==4
                assert campaign.coverage(pool)['replay_verified']==1
                campaign.register_pool(pool+'-alias',spec,[1,2,3,4])
                try: campaign.lease(pool+'-alias','new-owner',jobs=4)
                except LookupError: pass
                else: raise AssertionError('Completed alias reused')
                break
            abandoned+=1;clock[0]+=2 # Expire a COMMITTED lease; fresh identity next.
        if not accepted:
            try: campaign.lease(pool,'fourth-owner',jobs=4)
            except LookupError: pass
            else: raise AssertionError('Global three-challenge cap bypassed')
        if (trial+1)%250==0:print(trial+1,'trials',flush=True)
    expected=1-(3/4)**3; observed=successes/TRIALS
    se=math.sqrt(expected*(1-expected)/TRIALS)
    assert abs(observed-expected)<=6*se
    result=dict(scope='Actual SQLite leases, cryptographic random challenges, selective abandonment, identity changes and alias/cap enforcement. Correctness/replay is modeled with fixture bytes, not measured molecular computation or a network load test.',
        trials=TRIALS,n=4,q=1,correct_cached_units=1,max_challenges=3,
        successes=successes,committed_attempts=attempts,selective_abandonments=abandoned,
        theoretical_success=expected,observed_success=observed,theoretical_standard_error=se,
        theoretical_compute_units_per_success=1/expected,
        observed_modeled_compute_units_per_success=TRIALS/successes,
        global_cap_and_completed_alias_checks_passed=True,wall_seconds=time.perf_counter()-begin)
    (ROOT/'docs/evaluation/vina_followup_2026-09-12/cached_retry_scheduler.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
