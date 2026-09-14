"""Implemented admission attacks plus exact cost models; local output only."""
import hashlib,json,math,statistics,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.pool_admission import PoolAdmission

OUT=ROOT/'local-research/admission-2026-09-14';OUT.mkdir(parents=True,exist_ok=True)
spec=dict(model_version='fixture-only',receptor='r',ligand='l',conformer_bank='i',region='b',search_parameters={'max_evals':256000})
rows=[]
for policy,p in [('immediate',.05),('immediate',.1),('deferred',.05),('deferred',.1)]:
 with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as tmp:
  clock=[0.];c=PoolAdmission(Path(tmp)/'policy.sqlite',clock=lambda:clock[0],policy=policy,audit_probability=p)
  grants=replays=0;latencies=[];trials=400
  for i in range(trials):
   clock[0]+=60;owner='trusted-fixture-'+str(i);pool=str(i);c.register_pool(pool,{**spec,'conformer_bank':str(i)},[1]);c.grant_trust(owner,allowance=1)
   start=time.perf_counter();l=c.request(pool,owner);outputs={t['task']:b'fabricated' for t in l['tasks']};ch=c.commit(l['lease'],owner,l['binding'],c.output_root(l['binding'],outputs));s=c.submit(l['lease'],owner,l['binding'],ch['id'],outputs)
   if s['status']=='granted':c.redeem(l['lease'],owner);grants+=1
   if ch['replay_required']:
    replays+=1;verdicts={t:(hashlib.sha256(v).hexdigest(),False) for t,v in outputs.items()};c.replay(l['lease'],verdicts)
   latencies.append(1000*(time.perf_counter()-start))
  expected=1-p if policy=='immediate' else 1;se=math.sqrt(expected*(1-expected)/trials)
  assert abs(grants/trials-expected)<6*se+1e-12
  rows.append(dict(policy=policy,p=p,trials=trials,zero_compute_grants=grants,replays=replays,success_observed=grants/trials,success_expected=expected,control_plane_ms_median=statistics.median(latencies),control_plane_ms_p95=sorted(latencies)[int(.95*trials)],scope='Actual SQLite, commitment, CSPRNG challenge and credit transitions. Trusted eligibility explicitly granted by fixture. Molecular replay verdict is modeled, not timed here.'))

models=[]
for n,q in [(2,1),(4,1),(4,2),(8,1)]:
 for correct in range(n+1):
  probability=math.comb(correct,q)/math.comb(n,q) if correct>=q else 0
  success=1-(1-probability)**3
  models.append(dict(n=n,q=q,correct=correct,p=probability,cached_three_attempt_success=success,fresh_compute_per_grant=correct/probability if probability else None,cached_compute_per_grant=correct/success if success else None,server_replay_per_honest_grant=q,server_replay_per_attack_grant=q/probability if probability else None,server_replay_per_selective_abort_grant=q if probability else None))
exposure=[]
for p in [.05,.1,.25]:
 for cap in [5,10,20]:
  immediate=sum((1-p)**j for j in range(1,cap+1));deferred=sum((1-p)**j for j in range(cap))
  exposure.append(dict(p=p,allowance=cap,immediate_bad_grants=immediate,deferred_bad_grants=deferred,expected_replays_until_first_detection=p*deferred,identity_or_farming_cost_needed_for_one_unit_per_bad_grant=immediate,scope='Persistent zero-work identity, cap consumed by attempts, no extra admissions while selected audit pending. Values condition on retaining low-risk eligibility; actual reputation may stop earlier.'))
result=dict(implemented_attacks=rows,bundles=models,exposure=exposure,recommended=dict(trusted_policy='immediate',audit_probability=.1,allowance=10,trust_ttl_seconds=3600,untrusted_bundle=4,q=1,global_pending=16,per_identity_pending=1,notes=['These are configurable research operating points, not empirically optimal settings.','At zero trusted identity acquisition cost, a zero-work fresh trusted identity passes with probability 0.9. New identities are deliberately ineligible.','Automatic trust renewal by unaudited success is forbidden.','Retries retain existing global per-unit cap of three.','Late failures quarantine scientific aggregates and unused credits; consumed access cannot be revoked.','Application token bucket cannot prevent pre-application network floods.','Payload hashing and storage scale with submitted bytes; replay economics are not total server cost.']))
(OUT/'policy_results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2));print('Wrote local policy results')
