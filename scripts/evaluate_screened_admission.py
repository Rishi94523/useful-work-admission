"""Amendment 20: actual in-memory SQLite policy, modeled arrivals/verdicts/time.

No Cloudflare accuracy, native molecular execution, or endpoint capacity measured.
Latency is from committed submission, excluding client computation and Siteverify.
"""
import heapq
import hashlib
import json
import random
import sqlite3
import statistics
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.screened_admission import ScreenedAdmission
from research.ticket_admission import encoded

REPLAY = 1.4957105


class MemoryPolicy(ScreenedAdmission):
    @contextmanager
    def db(self):
        if not hasattr(self, 'connection'):
            self.connection = sqlite3.connect(':memory:', isolation_level=None)
            self.connection.row_factory = sqlite3.Row
        db = self.connection; db.execute('BEGIN IMMEDIATE')
        try:
            yield db; db.commit()
        except BaseException:
            db.rollback(); raise


def arrivals(rate, rng):
    at = 0
    while rate:
        at += rng.expovariate(rate)
        if at >= 120: return
        yield at


def run(mode, attack_rate, bypass, honest_pass, seed):
    now = [0.]; accepted_screen = [False]
    c = MemoryPolicy(':memory:', hashlib.sha256(f'key-{seed}'.encode()).digest(), {'campaign':'amendment20-fixture'},
                     clock=lambda:now[0], issuance_rate=1000, ttl=120, mode=mode,
                     verify_screen=lambda token,binding:accepted_screen[0])
    ids = random.Random(90000+seed)
    events=[]; serial=0
    for kind, rate, offset in [('honest',.2,100), ('trusted',.2,200), ('attack',attack_rate,300)]:
        rng=random.Random(seed+offset)
        for index,at in enumerate(arrivals(rate,rng)):
            serial+=1; heapq.heappush(events,(at,serial,'arrival',(kind,f'{kind}-{index}',rng.random())))
    counts=Counter(); busy={lane:False for lane in c.LANES}; jobs={}; delays=[]
    def admit(identity):
        owner,kind,at=jobs[identity]
        if c.redeem(identity,owner):
            counts[kind+'_admitted']+=1
            if now[0]-at<=5: counts[kind+'_deadline']+=1
            if kind=='honest': delays.append(now[0]-at)
    def dispatch():
        nonlocal serial
        for lane in c.LANES:
            if not busy[lane]:
                row=c.claim(lane)
                if row:
                    busy[lane]=True; serial+=1
                    heapq.heappush(events,(now[0]+REPLAY,serial,'finish',(lane,row)))
    with patch('research.screened_admission.secrets.token_hex', lambda n:ids.randbytes(n).hex()):
        while events:
            at,_,event,value=heapq.heappop(events)
            if at>150: break
            now[0]=at
            if event=='finish':
                lane,row=value; kind=jobs[row['id']][1]; good=kind!='attack'
                c.finish(row['id'],(row['root'],good),lambda db,r:None)
                counts['replays']+=1; counts[lane+'_replays']+=1
                if good: counts['verified_honest_bundles']+=1
                else: counts['quarantines']+=1
                admit(row['id']); busy[lane]=False
            else:
                kind,owner,coin=value; counts[kind+'_arrivals']+=1
                if mode!='none' and kind!='trusted':
                    accepted_screen[0]=coin<(bypass if kind=='attack' else honest_pass)
                    if c.promote(owner,'fixture-token-'+owner): counts[kind+'_screened']+=1
                ticket=c.issue(owner,trusted=kind=='trusted')
                if ticket['status']!='ticket': counts[ticket['status']]+=1; continue
                t=ticket['assignment']
                if kind!='attack' and not (mode=='screen_only' and t['tier']=='provisional'):
                    counts['honest_assigned_units']+=len(t['seeds'])
                body=encoded({str(s):'fabricated' if kind=='attack' else 'honest' for s in t['seeds']})
                response=c.submit(ticket['ticket'],hashlib.sha256(body).hexdigest(),body,owner)
                if response['status']=='accepted':
                    jobs[response['id']]=(owner,kind,at); admit(response['id'])
                else: counts[kind+'_'+response['status']]+=1
            dispatch()
    with c.db() as db:
        counts['unverified_retained']=db.execute("SELECT count(*) FROM queue WHERE state='UNVERIFIED' AND payload IS NOT NULL").fetchone()[0]
        counts['unverified_retained_bytes']=db.execute("SELECT coalesce(sum(length(payload)),0) FROM queue WHERE state='UNVERIFIED'").fetchone()[0]
    c.connection.close()
    return dict(mode=mode,attack_rate=attack_rate,bypass=bypass,honest_pass=honest_pass,seed=seed,
                counts=dict(counts),modeled_replay_cpu_s=counts['replays']*REPLAY,
                modeled_honest_compute_s=counts['honest_assigned_units']*REPLAY,
                honest_median_submission_delay_s=statistics.median(delays) if delays else None)


def main():
    out=ROOT/'local-research/screened-admission-2026-09-29'; out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for mode in ('none','screen_only','mandatory','deferred'):
        for attack in (0,1,10,100):
            for bypass in (.001,.01,.1,1):
                for hp in (.95,1):
                    for seed in range(5): rows.append(run(mode,attack,bypass,hp,seed))
            print(mode,'attack rate',attack,'completed',len(rows),'cases',flush=True)
        print(mode,'completed',len(rows),'cases',flush=True)
    result=dict(protocol='20',evidence='real policy ledger; simulated clock, screening and verdicts; tiny payload fixtures',
                replay_s=REPLAY,rows=rows,limitations=['No measured Turnstile false acceptance or latency',
                'No device quota assumed','Unsampled science expires without contributing to aggregate',
                'No raw HTTP, signature or Siteverify CPU/network capacity measurement',
                'Three reserved workers in all policies; screening-only can leave workers idle',
                'No overload entry puzzle in this isolated comparison',
                'Latency starts at submission; molecular client cost modeled separately'])
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    summary=[]
    for mode in ('none','screen_only','mandatory','deferred'):
        for bypass in (.001,.01,.1,1):
            group=[r for r in rows if r['mode']==mode and r['attack_rate']==100 and r['bypass']==bypass and r['honest_pass']==1]
            c=Counter()
            for r in group: c.update(r['counts'])
            summary.append(dict(mode=mode,bypass=bypass,honest_deadline=f"{c['honest_deadline']}/{c['honest_arrivals']}",
                                trusted_deadline=f"{c['trusted_deadline']}/{c['trusted_arrivals']}",
                                attack_admitted=c['attack_admitted'],replay_cpu_s=round(sum(r['modeled_replay_cpu_s'] for r in group),2),
                                unverified_retained=c['unverified_retained']))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
