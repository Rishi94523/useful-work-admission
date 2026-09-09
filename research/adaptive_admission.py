"""Conventional stateful outer control for the whole-run research scheduler.

Identity is supplied by a trusted session boundary, not claimed to be Sybil-proof.
All policy/lease/credit transitions use the same SQLite write transaction.
The trusted verifier alone calls finish; this module never accepts client verdicts.
"""
import hashlib
import json
import secrets
from time import perf_counter
from research.docking_campaign import canonical
from research.whole_run_campaign import WholeRunCampaign


class AdaptiveAdmission(WholeRunCampaign):
    VERSION = 'adaptive-outer-v2'
    # Chosen from measured browser.json tiers, not predicted from instruction count.
    TIERS = {'low': (1, 16, 4000, 4), 'medium': (4, 16, 16000, 8),
             'high': (16, 16, 16000, 8)}

    def __init__(self, path, clock=None, global_burst=32, global_rate=2):
        super().__init__(path, clock)
        self.global_burst, self.global_rate = global_burst, global_rate
        with self.transaction() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS risk(identity TEXT PRIMARY KEY,score REAL NOT NULL,
                updated REAL NOT NULL,streak INTEGER NOT NULL,cooldown REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS requests(identity TEXT,at REAL);
              CREATE INDEX IF NOT EXISTS recent_requests ON requests(identity,at);
              CREATE TABLE IF NOT EXISTS admission(lease TEXT PRIMARY KEY,tier TEXT,q INTEGER);
              CREATE TABLE IF NOT EXISTS risk_events(identity TEXT,at REAL,kind TEXT,delta REAL,score REAL);
              CREATE TABLE IF NOT EXISTS range_failures(task TEXT PRIMARY KEY,failures INTEGER);
              CREATE TABLE IF NOT EXISTS admission_budget(id INTEGER PRIMARY KEY,tokens REAL,updated REAL);
              CREATE INDEX IF NOT EXISTS adaptive_lease_expiry ON leases(status,expires);
              CREATE INDEX IF NOT EXISTS adaptive_lease_owner ON leases(owner,status);
            ''')
            db.execute('INSERT OR IGNORE INTO admission_budget VALUES(1,?,?)',
                       (global_burst, self.clock()))

    def lease(self, *args, **kwargs):
        raise ValueError('Adaptive deployments must use request(), not the base lease API')

    def _state(self, db, identity, now):
        db.execute('INSERT OR IGNORE INTO risk VALUES(?,0,?,0,0)', (identity, now))
        row = dict(db.execute('SELECT * FROM risk WHERE identity=?', (identity,)).fetchone())
        row['score'] = max(0, row['score'] - max(0, now-row['updated'])/120)
        row['updated'] = now
        return row

    def _save(self, db, state):
        db.execute('UPDATE risk SET score=?,updated=?,streak=?,cooldown=? WHERE identity=?',
                   (state['score'], state['updated'], state['streak'], state['cooldown'], state['identity']))

    def _event(self, db, identity, now, kind, delta, failure=False, success=False):
        state = self._state(db, identity, now)
        state['score'] = min(100, max(0, state['score']+delta))
        if failure: state['streak'] += 1
        if success: state['streak'] = max(0, state['streak']-1)
        self._save(db, state)
        db.execute('INSERT INTO risk_events VALUES(?,?,?,?,?)',
                   (identity, now, kind, delta, state['score']))
        return state

    def _expire(self, db, now):
        # Called inside request/finish transactions; each expired lease counted once.
        expired = db.execute("SELECT owner,status FROM leases WHERE expires<=? AND status IN ('OPEN','COMMITTED')", (now,)).fetchall()
        super()._expire(db, now)
        for row in expired:
            self._event(db, row['owner'], now, 'abandon_'+row['status'].lower(),
                        12 if row['status']=='COMMITTED' else 8, failure=True)

    @staticmethod
    def tier(score):
        return 'high' if score >= 35 else 'medium' if score >= 15 else 'low'

    def request(self, campaign, identity):
        if not isinstance(identity, str) or not 1 <= len(identity) <= 128:
            raise ValueError('Invalid trusted identity key')
        now = self.clock()
        with self.transaction() as db:
            self._expire(db, now)
            # Global issuance budget also covers identity churn. It does not stop
            # pre-application network floods or prevent attackers consuming capacity.
            bucket = db.execute('SELECT * FROM admission_budget WHERE id=1').fetchone()
            tokens = min(self.global_burst, bucket['tokens']+max(0, now-bucket['updated'])*self.global_rate)
            db.execute('UPDATE admission_budget SET tokens=?,updated=? WHERE id=1', (tokens-1 if tokens>=1 else tokens,now))
            if tokens < 1: return {'status':'capacity','reason':'global-rate-budget'}
            risk_start = perf_counter()
            state = self._state(db, identity, now)
            if state['cooldown'] > now:
                self._save(db, state)
                return {'status':'cooldown','risk':state['score'],'retry_after':state['cooldown']-now}
            db.execute('DELETE FROM requests WHERE at<?', (now-10,))
            velocity = db.execute('SELECT count(*) FROM requests WHERE identity=?', (identity,)).fetchone()[0]+1
            db.execute('INSERT INTO requests VALUES(?,?)', (identity,now))
            delta = (6 if velocity > 3 else 0) + min(8,2*state['streak'])
            state = self._event(db, identity, now, 'request', delta)
            if state['score'] >= 60:
                state['cooldown'] = now+60; self._save(db,state)
                return {'status':'cooldown','risk':state['score'],'retry_after':60}
            if db.execute("SELECT 1 FROM leases WHERE owner=? AND status IN ('OPEN','COMMITTED')", (identity,)).fetchone():
                return {'status':'pending','risk':state['score'],'reason':'one-outstanding-lease'}
            if db.execute("SELECT count(*) FROM leases WHERE status IN ('OPEN','COMMITTED')").fetchone()[0] >= 16:
                return {'status':'capacity','risk':state['score'],'reason':'global-outstanding-budget'}
            tier = self.tier(state['score']); jobs,runs,cap,q = self.TIERS[tier]
            risk_ms = (perf_counter()-risk_start)*1000
            candidates = self._lease_candidates(db,campaign)
            chosen=[]; ligands=set()
            for row in candidates:
                spec=json.loads(row['specification'])
                if row['ligand'] in ligands or row['stop']-row['start']!=runs or spec['search_parameters']['cap']!=cap: continue
                chosen.append(row);ligands.add(row['ligand'])
                if len(chosen)==jobs:break
            if len(chosen)!=jobs:
                return {'status':'capacity','risk':state['score'],'tier':tier,'reason':'scientific-pool'}
            tasks=[{'task':r['task'],'spec':json.loads(r['specification']),'start':r['start'],
                    'count':r['stop']-r['start'],'estimated_cost':r['cost']} for r in chosen]
            lease=secrets.token_hex(16)
            payload={'lease':lease,'campaign':campaign,'expires':now+120,'tasks':tasks,
                     'policy':self.VERSION,'tier':tier,'q':q}
            binding=hashlib.sha256(canonical(payload)).hexdigest();payload['binding']=binding
            db.execute('INSERT INTO leases(id,owner,issued,expires,status,tasks,binding) VALUES(?,?,?,?,?,?,?)',
                       (lease,identity,now,now+120,'OPEN',canonical(tasks).decode(),binding))
            db.execute('INSERT INTO admission VALUES(?,?,?)',(lease,tier,q))
            for row in chosen:db.execute("UPDATE units SET state='LEASED',lease=? WHERE task=?",(lease,row['task']))
            return {'status':'assigned','risk':state['score'],'velocity_10s':velocity,'risk_processing_ms':risk_ms,**payload}

    def commit(self, lease, owner, binding, commitment, samples=None, weighted=False):
        with self.transaction() as db:
            row=db.execute('SELECT q FROM admission WHERE lease=?',(lease,)).fetchone()
            if not row:raise ValueError('Missing adaptive admission policy')
            if weighted or (samples is not None and samples!=row['q']):raise ValueError('Client cannot reduce audit policy')
            q=row['q']
        return super().commit(lease,owner,binding,commitment,samples=q)

    def finish(self, lease, owner, binding, challenge_id, commitment, accepted, result):
        if type(accepted) is not bool:raise ValueError('Trusted Boolean verdict required')
        with self.transaction() as db:
            row=self._live(db,lease,owner,binding,'COMMITTED')
            if json.loads(row['challenge'])['id']!=challenge_id or row['commitment']!=commitment:
                raise ValueError('Challenge or commitment substitution')
            tasks=json.loads(row['tasks']); prior=0
            if not accepted:
                for task in tasks:
                    old=db.execute('SELECT failures FROM range_failures WHERE task=?',(task['task'],)).fetchone()
                    prior=max(prior,old['failures'] if old else 0)
                    db.execute('INSERT INTO range_failures VALUES(?,1) ON CONFLICT(task) DO UPDATE SET failures=failures+1',(task['task'],))
            risk_start=perf_counter()
            state=self._event(db,owner,self.clock(),'success' if accepted else 'audit_failure',
                              -2 if accepted else 18+min(6,2*prior),failure=not accepted,success=accepted)
            risk_ms=(perf_counter()-risk_start)*1000
            db.execute('UPDATE leases SET status=?,result=? WHERE id=?',
                       ('ACCEPTED' if accepted else 'REJECTED',canonical(result).decode(),lease))
            if accepted:db.execute("UPDATE units SET state='COMPLETED',completed_lease=?,lease=NULL WHERE lease=? AND state='LEASED'",(lease,lease))
            else:db.execute("UPDATE units SET state='EXPIRED',lease=NULL WHERE lease=? AND state='LEASED'",(lease,))
            return {'accepted':accepted,'risk':state['score'],'risk_processing_ms':risk_ms,'next_tier':self.tier(state['score']) if state['score']<60 else 'cooldown'}

    def risk_state(self, identity):
        with self.transaction() as db:
            self._expire(db,self.clock());state=self._state(db,identity,self.clock());self._save(db,state)
            return state
