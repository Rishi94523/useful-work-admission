"""Sampling experiments over committed honest/lower-budget whole-run outputs.

This quantifies sampling, not a lower bound on execution complexity: f denotes
the fraction whose complete outputs an attacker can reproduce correctly, which
can include cached/precomputed/shared work. No new molecular timing is inferred.
"""
import hashlib,json,math,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10'
source=ROOT/'tmp/vina-tasks/campaign/fa10/crystal_source/normal'
payloads=[(source/f'{i}.task').read_bytes()+(source/f'{i}.task.trace').read_bytes() for i in range(32)]
hashes=[hashlib.sha256(p).digest() for p in payloads]
short=source.parent/'16000'
short_hashes=[hashlib.sha256((short/f'{i}.task').read_bytes()+(short/f'{i}.task.trace').read_bytes()).digest() for i in range(32)]
assert all(a!=b for a,b in zip(hashes,short_hashes))
rng=random.Random(104729);rows=[];trials=20000
for n in [1,8,32]:
 for fraction in [.1,.25,.5,.75,.9,1.0]:
  correct=math.floor(n*fraction)
  # Lower-budget substitutions are fixed before independent challenge draws. Reference
  # hashes substitute for already validated replay outcomes in this simulation.
  submitted=hashes[:correct]+short_hashes[correct:n]
  for q in sorted(set([1,min(2,n),min(4,n),min(8,n)])):
   passes=sum(all(submitted[i]==hashes[i] for i in rng.sample(range(n),q)) for _ in range(trials))
   probability=math.comb(correct,q)/math.comb(n,q) if correct>=q else 0
   observed=passes/trials;z=1.96;den=1+z*z/trials;center=(observed+z*z/(2*trials))/den;radius=z*math.sqrt(observed*(1-observed)/trials+z*z/(4*trials*trials))/den
   rows.append({'n':n,'requested_fraction':fraction,'correct_runs':correct,'actual_fraction':correct/n,'q':q,'theory':probability,'passes':passes,'trials':trials,'observed':observed,'wilson95':[center-radius,center+radius],'ideal_equal_run_client_server_ratio':n/q,'three_attempt_cached_success':1-(1-probability)**3,'abstract_normal_work_per_accepted_bundle_three_attempts':correct/(1-(1-probability)**3) if probability else None})
result={'scope':'Implemented fixed-before-challenge lower-budget substitution sampling attacks using real raw-task/trace reference hashes, 20000 PRNG trials per setting. Reference-hash comparisons model replay verdicts; these are not repeated molecular replays or adversarial algorithm lower bounds. Fresh replay integration and browser measurements are separate.','substitution':'Each incorrect normal run is replaced with the actually computed 16k-cap output/trace for the same child seed; all32 substitutions disagree with the normal replay relation. Statistical trials reuse hashes, not molecular reruns.','rows':rows,'security':'For C correct committed outputs among N and uniform q distinct audits, P(pass)=choose(C,q)/choose(N,q). A single-run full audit has no within-request replay asymmetry. Cross-user pooling does not inherit the per-contributor bound. Multiple attempts increase success; for independent attempts p, at most 1-(1-p)^a across a attempts, before credit and admission costs.'}
(OUT/'audit_sampling.json').write_text(json.dumps(result,indent=2)+'\n');print('Completed',len(rows),'sampling settings')
