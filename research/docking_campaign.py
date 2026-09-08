"""Transactional research scheduler for disjoint scientific work.

SQLite prototype: not a production identity, throttling or distributed lock service.
Campaign names do not change scientific identity; model/input hashes do.
"""
from contextlib import contextmanager,closing
import hashlib
import json
import secrets
import sqlite3
import time
import bisect
import math


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


class Campaign:
    def __init__(self,path,clock=time.time):
        self.path=str(path);self.clock=clock
        with closing(self.connect()) as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS units(
              task TEXT PRIMARY KEY, family TEXT NOT NULL, campaign TEXT NOT NULL,
              ligand TEXT NOT NULL, start INTEGER NOT NULL, stop INTEGER NOT NULL,
              cost REAL NOT NULL CHECK(cost>0), specification TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('UNASSIGNED','LEASED','COMPLETED','EXPIRED')),
              lease TEXT, completed_lease TEXT);
            CREATE INDEX IF NOT EXISTS ranges ON units(family,start,stop);
            CREATE INDEX IF NOT EXISTS available ON units(state,ligand);
            CREATE TABLE IF NOT EXISTS leases(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, issued REAL NOT NULL, expires REAL NOT NULL,
              status TEXT NOT NULL, tasks TEXT NOT NULL, binding TEXT NOT NULL,
              commitment TEXT, challenge TEXT, result TEXT);
            ''')

    def connect(self):
        db=sqlite3.connect(self.path,timeout=10,isolation_level=None);db.row_factory=sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        db=self.connect()
        try:
            db.execute('BEGIN IMMEDIATE');yield db;db.commit()
        except BaseException:
            db.rollback();raise
        finally:db.close()

    def add(self,campaign,spec,start,count,cost):
        required={'model_version','receptor','ligand','conformer_bank','region','search_parameters'}
        if set(spec)!=required:raise ValueError('Incomplete scientific identity')
        if type(start)!=int or type(count)!=int or start<0 or not 1<=count<=16384 or not math.isfinite(cost) or cost<=0:raise ValueError('Invalid work range')
        family=hashlib.sha256(canonical(spec)).hexdigest()
        task=hashlib.sha256(canonical([family,start,count])).hexdigest()
        with self.transaction() as db:
            if db.execute('SELECT 1 FROM units WHERE family=? AND start<? AND stop>?',(family,start+count,start)).fetchone():
                raise ValueError('Scientific range overlaps registered work, including completed work')
            db.execute('INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?)',(task,family,campaign,spec['ligand'],start,start+count,cost,canonical(spec).decode(),'UNASSIGNED',None,None))
        return task

    def _expire(self,db,now):
        db.execute("UPDATE units SET state='EXPIRED',lease=NULL WHERE state='LEASED' AND lease IN (SELECT id FROM leases WHERE expires<=? AND status IN ('OPEN','COMMITTED'))",(now,))
        db.execute("UPDATE leases SET status='EXPIRED' WHERE expires<=? AND status IN ('OPEN','COMMITTED')",(now,))

    def lease(self,campaign,owner,jobs=1,ttl=60):
        if not 1<=jobs<=16 or not 0<ttl<=600 or not owner:raise ValueError('Invalid bounded lease request')
        now=self.clock();lease=secrets.token_hex(16)
        with self.transaction() as db:
            self._expire(db,now)
            # Random selection is a prototype policy, not a scalable SQL plan.
            candidates=db.execute("SELECT * FROM units WHERE campaign=? AND state IN ('UNASSIGNED','EXPIRED') ORDER BY RANDOM()",(campaign,)).fetchall()
            chosen=[];ligands=set()
            for row in candidates:
                if row['ligand'] in ligands:continue
                chosen.append(row);ligands.add(row['ligand'])
                if len(chosen)==jobs:break
            if len(chosen)!=jobs:raise LookupError('Insufficient distinct uncompleted ligand jobs')
            tasks=[{'task':r['task'],'spec':json.loads(r['specification']),'start':r['start'],'count':r['stop']-r['start'],'estimated_cost':r['cost']} for r in chosen]
            payload={'lease':lease,'campaign':campaign,'expires':now+ttl,'tasks':tasks}
            binding=hashlib.sha256(canonical(payload)).hexdigest();payload['binding']=binding
            db.execute('INSERT INTO leases(id,owner,issued,expires,status,tasks,binding) VALUES(?,?,?,?,?,?,?)',(lease,owner,now,now+ttl,'OPEN',canonical(tasks).decode(),binding))
            for row in chosen:db.execute("UPDATE units SET state='LEASED',lease=? WHERE task=?",(lease,row['task']))
        return payload

    def _live(self,db,lease,owner,binding,status):
        now=self.clock();self._expire(db,now)
        row=db.execute('SELECT * FROM leases WHERE id=?',(lease,)).fetchone()
        if not row or row['owner']!=owner or row['binding']!=binding or row['status']!=status or row['expires']<=now:
            raise ValueError('Lease owner, binding, state or deadline mismatch')
        return row

    def commit(self,lease,owner,binding,commitment,samples=32,weighted=False):
        if len(commitment)!=64 or any(c not in '0123456789abcdef' for c in commitment):raise ValueError('Invalid SHA256 commitment')
        if not 1<=samples<=128:raise ValueError('Invalid sample budget')
        with self.transaction() as db:
            row=self._live(db,lease,owner,binding,'OPEN');tasks=json.loads(row['tasks'])
            rng=secrets.SystemRandom()
            if weighted:
                # Independent with-replacement cost-weighted samples. Cost is
                # server calibration per pose, not a client-reported value.
                # Sample job by total calibrated cost, then pose uniformly.
                # O(jobs + samples), without materializing every pose.
                jobs=rng.choices(range(len(tasks)),weights=[t['estimated_cost'] for t in tasks],k=samples)
                chosen=[(j,rng.randrange(tasks[j]['count'])) for j in jobs]
            else:
                cumulative=[];total=0
                for t in tasks:total+=t['count'];cumulative.append(total)
                chosen=[]
                for flat in rng.sample(range(total),min(samples,total)):
                    j=bisect.bisect_right(cumulative,flat);chosen.append((j,flat-(cumulative[j-1] if j else 0)))
            challenge={'id':secrets.token_hex(16),'draws':chosen,'weighted_with_replacement':weighted}
            db.execute("UPDATE leases SET status='COMMITTED',commitment=?,challenge=? WHERE id=?",(commitment,canonical(challenge).decode(),lease))
        return challenge

    def finish(self,lease,owner,binding,challenge_id,commitment,accepted,result):
        # Caller is the trusted verifier, never a client-supplied success flag.
        with self.transaction() as db:
            row=self._live(db,lease,owner,binding,'COMMITTED')
            if json.loads(row['challenge'])['id']!=challenge_id or row['commitment']!=commitment:
                raise ValueError('Challenge or commitment substitution')
            status='ACCEPTED' if accepted else 'REJECTED'
            db.execute('UPDATE leases SET status=?,result=? WHERE id=?',(status,canonical(result).decode(),lease))
            if accepted:
                db.execute("UPDATE units SET state='COMPLETED',completed_lease=?,lease=NULL WHERE lease=? AND state='LEASED'",(lease,lease))
            else:db.execute("UPDATE units SET state='EXPIRED',lease=NULL WHERE lease=? AND state='LEASED'",(lease,))
        return accepted

    def snapshot(self):
        with self.transaction() as db:
            self._expire(db,self.clock())
            return {'units':dict(db.execute('SELECT state,count(*) FROM units GROUP BY state').fetchall()),'leases':dict(db.execute('SELECT status,count(*) FROM leases GROUP BY status').fetchall())}
