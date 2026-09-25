"""Score every amendment-12 seed without changing the predeclared gates.

Creates local summary/claim-check files. Legacy rows remain separate. Ranges
are min/max across five seeds, not confidence intervals for production traffic.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_admission_amendment12 import OUT, SEEDS, grid, key
from scripts.evaluate_priority_admission import DEVICES, REPLAY_S, PATIENCE_S, CORE_RATE, HONEST_EVERY_S

LAM = 1 / HONEST_EVERY_S


def read(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def spread(values):
    values = [v for v in values if v is not None]
    return dict(n=len(values), mean=statistics.mean(values), minimum=min(values), maximum=max(values)) if values else None


def cell_id(r):
    if r['grid'] in ('follow', 'patience'):
        return (r['grid'], r['mechanism'], r['workers'], r['attacker_cores'])
    return (r['grid'], r['workers'], r['attacker_cores'], r['attested_share'], r['attacker_tokens_per_s'])


def checks(rows, *, paired_seed=True):
    out = []
    def add(name, r, group, observed, comparison, bound):
        passed = observed >= bound-1e-12 if comparison == '>=' else observed <= bound+1e-12
        out.append(dict(prediction=name, seed=r['seed'], cell=cell_id(r), group=group,
                        observed=observed, comparison=comparison, bound=bound, passed=passed))
    prior = {(r['workers'], r['attacker_cores'], r['seed'] if paired_seed else None):r
             for r in rows if r['grid']=='patience'}
    for r in rows:
        rate = r['workers']/REPLAY_S
        cores = r['attacker_cores']
        if r['grid'] in ('follow', 'patience') and r['mechanism']=='priority' and cores>0:
            for cls, g in r['classes'].items():
                threshold = max(0, rate-LAM)*DEVICES[cls]*PATIENCE_S/CORE_RATE
                if cores < threshold/2: add('C1_'+r['grid'],r,cls,g['served'],'>=',.9)
                elif cores > 2*threshold: add('C1_'+r['grid'],r,cls,g['served'],'<=',.5)
        if r['grid']=='oneshot':
            share, tokens = r['attested_share'], r['attacker_tokens_per_s']
            demand = LAM*share+tokens
            for name,g in r['groups'].items():
                cls, lane = name.split('/')
                if lane=='attested':
                    if demand<=.8*rate: add('A1',r,name,g['served'],'>=',.9)
                    if demand>=1.25*rate: add('A2',r,name,g['served'],'<=',rate/demand+.1)
                    add('A6',r,name,int(g['fallbacks']>0 or g['puzzle_s_total']==0),'>=',1)
                else:
                    if demand>=1.25*rate: add('A2',r,name,g['served'],'<=',.2)
                    if share<=.5 and cores>0 and g['users']>=20:
                        threshold=max(0,rate-LAM-tokens)*DEVICES[cls]*PATIENCE_S/CORE_RATE
                        if cores<threshold/2: add('A3',r,name,g['served'],'>=',.9)
                        elif cores>2*threshold: add('A3',r,name,g['served'],'<=',.5)
                    if share==0 and tokens==0:
                        p=prior[(r['workers'],cores,r['seed'] if paired_seed else None)]
                        add('A4',r,name,abs(g['served']-p['classes'][cls]['served']),'<=',.10)
        if r['grid']=='bootstrap' and cores==16:
            share,tokens=r['attested_share'],r['attacker_tokens_per_s']
            for name,g in r['groups'].items():
                if share==0 or name.endswith('/anonymous'): add('A5',r,name,g['trusted'],'<=',.1)
                elif tokens<=.1: add('A5',r,name,g['trusted'],'>=',.9)
                elif tokens==10: add('A5',r,name,g['trusted'],'<=',.5)
    return out


def counts(items):
    grouped=defaultdict(list)
    for r in items: grouped[r['prediction']].append(r)
    return {name:dict(passed=sum(r['passed'] for r in group), eligible=len(group),
                     by_seed={str(seed):dict(passed=sum(r['passed'] for r in group if r['seed']==seed),
                                             eligible=sum(r['seed']==seed for r in group))
                              for seed in sorted({r['seed'] for r in group})})
            for name, group in grouped.items()}


def legacy():
    paths={'follow':'priority-admission-2026-09-24', 'patience':'priority-admission-2026-09-24-patience',
           'oneshot':'attested-admission-2026-09-25/oneshot', 'bootstrap':'attested-admission-2026-09-25/bootstrap'}
    return [dict(r,grid=g) for g,p in paths.items() for r in read(ROOT/'local-research'/p/'results.jsonl')]


def main():
    ledger=OUT/'results.jsonl'
    rows=read(ledger)
    assert len(rows)==1120 and {r['job_key'] for r in rows}=={key(j) for j in grid()}, 'Incomplete or duplicate grid'
    assert all(r['timing']['mode']=='exact-replay-events' and r['timing']['service_s']==1.52 for r in rows)
    grouped=defaultdict(list)
    for r in rows: grouped[cell_id(r)].append(r)
    aggregates=[]
    for cell, rs in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        assert sorted(r['seed'] for r in rs)==list(SEEDS)
        groups={}
        group_name='classes' if rs[0]['grid'] in ('follow','patience') else 'groups'
        for name,g in rs[0][group_name].items():
            fields=('served','paid_s_median','paid_s_p95') if group_name=='classes' else ('served','trusted','trust_s_median','puzzle_s_total','fallbacks')
            groups[name]={f:spread([r[group_name][name].get(f) for r in rs]) for f in fields}
            groups[name]['users_per_seed']=g.get('users',g.get('arrivals'))
        aggregates.append(dict(cell=cell,groups=groups))
    checks_now=checks(rows);old=legacy();checks_old=checks(old,paired_seed=False)
    summary=dict(complete=True, runs=len(rows), seeds=SEEDS, cells=len(aggregates),
                 ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(),
                 checks=counts(checks_now), original_checks=counts(checks_old), aggregates=aggregates,
                 note='Mean and observed min/max across five seeds; not production confidence bounds. C1 excludes the half-to-double threshold band.')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (OUT/'prediction_checks.json').write_text(json.dumps(checks_now,indent=2),encoding='utf-8')
    for name,item in summary['checks'].items():
        old=summary['original_checks'].get(name,{})
        print(f"{name}: original {old.get('passed')}/{old.get('eligible')}; corrected {item['passed']}/{item['eligible']}; seeds {item['by_seed']}")
    print('COMPLETE',len(rows),'runs; summary',OUT/'summary.json')


if __name__=='__main__':
    main()
