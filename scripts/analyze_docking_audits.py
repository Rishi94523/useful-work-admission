"""Measure real Merkle commitments and expose raw-transition sampling's gap."""
import json
from pathlib import Path
import random
import statistics
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research.merkle_search_audit import Tree,verify_opening,accept_probability,minimum_samples,encoded
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'

def main():
    rng=random.Random(20260907)
    evidence={'scope':'Exact combinatorial probabilities and a local raw-Merkle implementation. Transition counterexample is a mathematical diagnostic, not a proposed scientific workload. Native score-check cost estimates are explicitly projections from the prior pilot.','probabilities':[],'transition_splice':[]}
    # Binding index, task and score does not imply that all committed scores are true.
    for n in [16,32,64,128,256,4096]:
        for bad in sorted({1,max(1,n//100),max(1,n//10),n//2,3*n//4}):
            for q in [1,4,8,16,32,64]:
                if q>n:continue
                p=accept_probability(n,bad,q)
                evidence['probabilities'].append({'n':n,'bad_positions':bad,'q':q,'accept_probability_exact':p,'with_replacement_bound':((n-bad)/n)**q,'success_in_100_independent_attempts':-math.expm1(100*math.log1p(-p)) if p<1 else 1})
        # An absorbing search transition F(x)=max(x-1,0). A jump into the fixed
        # point needs one invalid edge, while the remaining suffix is all valid.
        states=[n]+[0]*n
        rows=[{'task':'splice-demo','index':i,'before':states[i],'after':states[i+1]} for i in range(n)]
        tree=Tree(rows);q=min(16,n);accepted=0;trials=10000
        for _ in range(trials):
            indexes=rng.sample(range(n),q)
            # Logical checking; separately time actual Merkle path checks below.
            accepted+=all(states[i+1]==max(states[i]-1,0) for i in indexes)
        timings=[]
        for _ in range(20):
            selected=rng.sample(range(n),q);begin=time.perf_counter()
            for index in selected:assert verify_opening(tree.root,tree.opening(index),n)
            timings.append((time.perf_counter()-begin)*1000)
        evidence['transition_splice'].append({'n':n,'invalid_edges':1,'q':q,'accept_probability_exact':1-q/n,'simulated_accept_fraction':accepted/trials,'simulation_trials':trials,'audit_merkle_ms_median':statistics.median(timings),'proof_bytes_uncompressed_json':sum(len(encoded(tree.opening(i))) for i in range(q)),'work_skipped':'N-1 decrement transitions; one forged first transition then a valid absorbing suffix. Commitment still costs O(N) hashes.'})
    evidence['required_samples']=[{'n':n,'bad_positions':bad,'target_failure':target,'q_exact':minimum_samples(n,bad,target),'projected_native_check_ms_at_5ms_each':5*minimum_samples(n,bad,target)} for n in [256,4096] for bad in sorted({1,n//100,n//10,n//2}) for target in [1e-3,1e-6,2**-40]]
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'audits.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'required_samples_256':[r for r in evidence['required_samples'] if r['n']==256],'transition_splice':evidence['transition_splice']},indent=2))

if __name__=='__main__':
    import math
    main()
