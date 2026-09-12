"""Paired compound bootstrap; repeated seeds are not independent compounds."""
import json, math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/evaluation/vina_followup_2026-09-12'
SEEDS=[104729,130363,155921]

def read(name):
    p=BASE/name
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

def auc(a,d): return float(((a[:,None]<d)+.5*(a[:,None]==d)).mean())

def ef(scores, labels):
    # Average fractional tie occupancy at the cutoff, independent of row order.
    k=math.ceil(.1*len(scores)); cutoff=np.sort(scores)[k-1]
    lower=scores<cutoff; tied=scores==cutoff
    hits=float(labels[lower].sum())+(k-int(lower.sum()))*float(labels[tied].mean())
    return hits/k/float(labels.mean())

def analyze(rows,expected):
    results=[]
    for target in sorted({r['target'] for r in rows}):
        tr=[r for r in rows if r['target']==target]
        by={(r['id'],r['seed']):r for r in tr}
        assert len(by)==len(tr), 'Duplicate experiment keys'
        ids=sorted({r['id'] for r in tr}); complete=len(ids)==expected and all((i,s) in by for i in ids for s in SEEDS)
        result=dict(target=target,complete=complete,compound_count=len(ids),paired_rows=len(tr),per_seed=[])
        for seed in SEEDS:
            rs=[r for r in tr if r['seed']==seed]
            if len(rs)!=expected: continue
            y=np.array([r['label']=='active' for r in rs]); n=np.array([r['normal_score'] for r in rs]); m=np.array([r['medium_score'] for r in rs])
            result['per_seed'].append(dict(seed=seed,normal_auc=auc(n[y],n[~y]),medium_auc=auc(m[y],m[~y]),
                normal_ef10=ef(n,y),medium_ef10=ef(m,y),
                evaluation_ratio=float(sum(r['medium_evals'] for r in rs)/sum(r['normal_evals'] for r in rs)),
                search_time_ratio=float(sum(r['medium_ms'] for r in rs)/sum(r['normal_ms'] for r in rs))))
        if complete:
            labels=np.array([by[(i,SEEDS[0])]['label']=='active' for i in ids])
            normal=np.array([[by[(i,s)]['normal_score'] for s in SEEDS] for i in ids])
            medium=np.array([[by[(i,s)]['medium_score'] for s in SEEDS] for i in ids])
            for i in ids:
                assert len({by[(i,s)]['input_sha256'] for s in SEEDS})==1
            active=np.flatnonzero(labels); decoy=np.flatnonzero(~labels)
            def delta(a,d):return [auc(medium[a,j],medium[d,j])-auc(normal[a,j],normal[d,j]) for j in range(3)]
            rng=np.random.default_rng(104729)
            boot=np.array([delta(rng.choice(active,len(active)),rng.choice(decoy,len(decoy))) for _ in range(5000)])
            ci=np.percentile(boot.mean(axis=1),[2.5,97.5]).tolist()
            result.update(mean_seed_auc_difference=float(np.mean(delta(active,decoy))),mean_difference_bootstrap95=ci,
                noninferiority_margin=-.05,noninferiority_established=ci[0]>-.05,
                meaningful_inferiority_supported=ci[1]<-.05,
                per_seed_difference_bootstrap95=np.percentile(boot,[2.5,97.5],axis=0).T.tolist())
        results.append(result)
    return results

stock=read('large_stock.jsonl')
result=dict(scope='Incomplete snapshots cannot establish noninferiority. Compound-resampled paired bootstrap preserves all three seeds together; seed variation is reported separately. New source conformers differ from the old MMFF panel.',
    stock_progress=[dict(target=t,completed=sum(r['target']==t for r in stock),expected=96,
        failures=sum(r['target']==t and not r['ok'] for r in stock)) for t in ['fa10','tryb1','esr1']],
    stock_gates=json.loads((BASE/'large_stock_gates.json').read_text()) if (BASE/'large_stock_gates.json').exists() else None,
    large_matched=analyze(read('large_matched.jsonl'),96),
    old_tryb1_diagnostic=analyze(read('tryb1_old_seed_diagnostic.jsonl'),8),
    limitations=['Stock gating and comparison on the same selected compounds characterize a conditional cohort, not an unbiased all-target generalization.',
        'Only three seeds: bootstrap intervals condition on these seeds and do not capture all search-seed uncertainty.',
        'Concurrent timings are not isolated throughput or browser timings.',
        'DUD-E active/decoy enrichment does not establish prospective screening utility.'])
(BASE/'followup_summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
