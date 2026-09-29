"""Read amendment-20 modeled results without turning assumed pass rates into measurements."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'local-research/screened-admission-2026-09-29'


def main():
    data=json.loads((OUT/'results.json').read_text()); rows=data['rows']
    assert len(rows)==640
    trusted={}
    for row in rows:
        c=row['counts']; seed=row['seed']
        outcome=(c.get('trusted_arrivals',0),c.get('trusted_deadline',0),c.get('trusted_admitted',0))
        if seed in trusted: assert trusted[seed]==outcome, (row,outcome,trusted[seed])
        trusted[seed]=outcome
        if row['mode'] in ('none','mandatory'): assert c.get('attack_admitted',0)==0
    table=[]
    for attack in (0,100):
        for bypass in (.001,.01,.1,1):
            for mode in ('none','screen_only','mandatory','deferred'):
                group=[r for r in rows if r['attack_rate']==attack and r['bypass']==bypass and r['mode']==mode and r['honest_pass']==1]
                c=Counter()
                for r in group: c.update(r['counts'])
                table.append(dict(attack_rate=attack,bypass=bypass,mode=mode,
                                  honest_deadline=c['honest_deadline'],honest_arrivals=c['honest_arrivals'],
                                  honest_percent=round(100*c['honest_deadline']/c['honest_arrivals'],1),
                                  attack_admissions=c['attack_admitted'],
                                  provisional_replay_cpu_s=round(c['provisional_replays']*data['replay_s'],3)))
    summary=dict(PN1=True,rows=len(rows),trusted_by_seed=trusted,table=table,
                 mandatory_stability_condition='honest_rate + attacker_rate * assumed_bypass < 1/replay_seconds',
                 max_stable_bypass_at_100_per_s=(1/data['replay_s']-.2)/100,
                 deferred_caveat='An unsampled output occupies bounded pending storage until expiry; no background repair worker is modeled.')
    (OUT/'analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
    files=['research/screened_admission.py','scripts/evaluate_screened_admission.py',
           'scripts/analyze_screened_admission.py','research/tests/test_screened_admission.py']
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),protocol_commit='4310d9e',
                  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
                  result_sha256=hashlib.sha256((OUT/'results.json').read_bytes()).hexdigest(),
                  evidence=data['evidence'])
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
