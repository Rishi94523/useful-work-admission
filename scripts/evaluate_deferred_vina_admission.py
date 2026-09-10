"""Policy economics outside the frozen whole-run protocol; no security upgrade claim."""
import json,math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10';OUT.mkdir(parents=True,exist_ok=True)
rng=np.random.default_rng(104729);rows=[];trials=100000
for p in [.01,.02,.05,.1,.25,1.]:
 for cap in [1,5,20,100]:
  for lag in [0,2,10]:
   # T is first audited fraudulent result. Access is granted before its verdict;
   # lag further admissions can occur, bounded by the identity exposure cap.
   first=rng.geometric(p,size=trials);grants=np.minimum(first+lag,cap)
   exact=sum((1-p)**max(0,k-lag) for k in range(cap))
   detection=1-(1-p)**cap
   rows.append({'audit_probability':p,'identity_grant_cap':cap,'verdict_lag_admissions':lag,'expected_bad_grants_exact':exact,'expected_bad_grants_simulated':float(grants.mean()),'mean_standard_error':float(grants.std(ddof=1)/math.sqrt(trials)),'eventual_detection_probability':detection,'no_detection_before_cap_probability':(1-p)**max(0,cap-lag),'honest_client_server_compute_ratio':1/p,'simulation_trials':trials})
bundle=[]
for n in [4,8,16,32,64,128]:
 for q in [1,2,4,8]:
  if q>n:continue
  for fraction in [.1,.25,.5,.75,.9]:
   c=math.floor(n*fraction);prob=math.comb(c,q)/math.comb(n,q) if c>=q else 0
   bundle.append({'n':n,'q':q,'correct_runs':c,'pass_probability':prob,'client_server_replay_ratio':n/q,'three_attempt_success':1-(1-prob)**3})
result={'scope':'Monte Carlo of policy exposure, not a deployed reputation experiment. All attacks submit zero-work invalid results; selected full-run replay detects them. Fresh identities are not assumed costly. Work-credit and audit implementations are unchanged.','deferred':rows,'immediate_bundles':bundle,'capacity':{'formula':'stable only if arrival_rate * audit_probability * replay_seconds < replay_worker_count (before headroom)','example_replay_seconds':.75,'one_worker_max_arrivals_per_second_at_p05':1/(.75*.05)},'interpretation':['Deferred access is already consumed even if its scientific credit is later rejected.','Unlimited cheap trusted identities bypass per-identity exposure caps.','Identity acquisition/reputation and global issuance limits are necessary external assumptions.','Unsampled scientific output remains provisional; audit probability is not an accuracy estimate for selected top-ranked poses.','These models do not establish that an unaudited accepted individual performed work.']}
(OUT/'deferred_policy.json').write_text(json.dumps(result,indent=2)+'\n')
assert all(abs(r['expected_bad_grants_exact']-r['expected_bad_grants_simulated'])<=6*r['mean_standard_error']+1e-8 for r in rows)
print(len(rows),'deferred settings;',len(bundle),'bundle settings; simulation agrees within six standard errors')
