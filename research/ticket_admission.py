"""Isolated four-part admission prototype; NOT the deployed PoolAdmission.

Server-authenticated sessions and scientific replay are trusted integrations.
Tickets allocate fresh seed ranges, not queue seats. A bounded SQLite queue
admits committed output, with independent newcomer/trusted reservations and
an overload-only, request-bound SHA-256 puzzle. No molecular code is changed.
"""
import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager


def encoded(x):
    return json.dumps(x, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class TicketAdmission:
    MAX_BODY = 600_000
    MAX_UNIT = 128_000

    def __init__(self, path, key, spec, *, clock=time.time, capacity=16,
                 byte_capacity=4_000_000, puzzle_bits=16, ttl=120, issuance_rate=2):
        if len(key) < 32 or capacity < 2 or capacity % 2 or not 1 <= puzzle_bits <= 24:
            raise ValueError('Configuration')
        self.path, self.key, self.spec = str(path), key, spec
        self.clock, self.capacity, self.byte_capacity = clock, capacity, byte_capacity
        self.bits, self.ttl = puzzle_bits, ttl
        if issuance_rate<=0: raise ValueError('Issuance rate')
        self.issuance_rate=issuance_rate
        self.spec_hash = hashlib.sha256(encoded(spec)).hexdigest()
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS config(id INTEGER PRIMARY KEY, spec TEXT);
            CREATE TABLE IF NOT EXISTS counters(id INTEGER PRIMARY KEY, next_seed INTEGER);
            CREATE TABLE IF NOT EXISTS budget(tier TEXT PRIMARY KEY,tokens REAL,at REAL);
            CREATE TABLE IF NOT EXISTS queue(id TEXT PRIMARY KEY,owner TEXT,tier TEXT,
              ticket TEXT,root TEXT,payload BLOB,draws TEXT,state TEXT,issued REAL,expires REAL);
            CREATE INDEX IF NOT EXISTS queue_state ON queue(state,tier);
            CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY,overload_until REAL);
            INSERT OR IGNORE INTO counters VALUES(1,0);
            INSERT OR IGNORE INTO control VALUES(1,0);
            ''')
            db.execute('INSERT OR IGNORE INTO config VALUES(1,?)', (self.spec_hash,))
            if db.execute('SELECT spec FROM config').fetchone()[0] != self.spec_hash:
                raise ValueError('Use a separate ledger for another scientific configuration')
            for tier in ('new', 'trusted'):
                db.execute('INSERT OR IGNORE INTO budget VALUES(?,32,?)', (tier,self.clock()))

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
        except BaseException:
            c.rollback(); raise
        finally:
            c.close()

    def seal(self, data):
        body = base64.urlsafe_b64encode(encoded(data)).decode()
        return body+'.'+hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()

    def open(self, token, purpose):
        if not isinstance(token,str) or len(token)>8192: raise ValueError('Token size')
        body, tag = token.split('.')
        expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(tag, expected): raise ValueError('MAC')
        d = json.loads(base64.urlsafe_b64decode(body))
        if d['purpose'] != purpose or d['expires'] <= self.clock(): raise ValueError('Expired/purpose')
        return d

    def issue(self, owner, *, trusted=False):
        # trusted is supplied by an authenticated server integration, never JSON input.
        if not isinstance(owner,str) or not 1<=len(owner)<=128: raise ValueError('Session')
        tier = 'trusted' if trusted else 'new'; n = 1 if trusted else 4; now = self.clock()
        with self.db() as db:
            b = db.execute('SELECT * FROM budget WHERE tier=?',(tier,)).fetchone()
            tokens = min(32,b['tokens']+max(0,now-b['at'])*self.issuance_rate)
            db.execute('UPDATE budget SET tokens=?,at=? WHERE tier=?',(tokens-1 if tokens>=1 else tokens,now,tier))
            if tokens<1: return {'status':'rate_limited'}
            start = db.execute('SELECT next_seed FROM counters').fetchone()[0]
            if start+n >= 2**30: return {'status':'seed_space_exhausted'}
            db.execute('UPDATE counters SET next_seed=?',(start+n,))
        d = dict(purpose='work',id=secrets.token_hex(16),owner=owner,tier=tier,
                 spec=self.spec_hash,seeds=list(range(start,start+n)),issued=now,expires=now+self.ttl)
        return {'status':'ticket','ticket':self.seal(d),'assignment':d,'inputs':self.spec}

    def _ticket(self, token, owner):
        t = self.open(token,'work')
        if t['owner'] != owner or t['spec'] != self.spec_hash: raise ValueError('Binding')
        return t

    def _expire(self, db):
        # Queue deadlines release bytes/seats; completed/failed receipts are retained
        # only until ticket expiry, after which the signed ticket cannot be reused.
        db.execute('DELETE FROM queue WHERE expires<=?',(self.clock(),))

    def _busy(self, db):
        self._expire(db)
        rows = db.execute("SELECT tier,count(*) n,coalesce(sum(length(payload)),0) b FROM queue WHERE state='QUEUED' GROUP BY tier").fetchall()
        total = sum(r['n'] for r in rows); size = sum(r['b'] for r in rows)
        if total>=self.capacity//2 or size>=self.byte_capacity//2:
            db.execute('UPDATE control SET overload_until=?',(self.clock()+5,))
        active = db.execute('SELECT overload_until FROM control').fetchone()[0]>self.clock()
        return active, {r['tier']:r['n'] for r in rows}, total, size

    def offer(self, ticket, root, owner):
        t = self._ticket(ticket,owner)
        if len(root)!=64 or any(c not in '0123456789abcdef' for c in root): raise ValueError('Root')
        with self.db() as db: busy,_,_,_ = self._busy(db)
        if t['tier']=='trusted' or not busy: return {'status':'ready'}
        p = dict(purpose='entry',ticket=t['id'],owner=owner,root=root,bits=self.bits,
                 expires=min(t['expires'],self.clock()+30))
        return {'status':'puzzle','challenge':self.seal(p),'bits':self.bits}

    def _proof(self, t, root, proof):
        if not isinstance(proof,dict) or set(proof)!={'challenge','nonce'}: return False
        try:
            p=self.open(proof['challenge'],'entry');n=proof['nonce']
            if type(n)!=int or not 0<=n<2**64: return False
            if (p['ticket'],p['owner'],p['root'],p['bits'])!=(t['id'],t['owner'],root,self.bits): return False
            digest=hashlib.sha256(proof['challenge'].encode()+n.to_bytes(8,'big')).digest()
            return int.from_bytes(digest,'big') < 2**(256-self.bits)
        except (ValueError,KeyError,TypeError): return False

    def submit(self, ticket, root, body, owner, proof=None):
        if not isinstance(body,bytes) or len(body)>self.MAX_BODY: return {'status':'too_large'}
        t = self._ticket(ticket,owner)
        # Input is fully committed before the secret audit sample is derived.
        if hashlib.sha256(body).hexdigest()!=root: raise ValueError('Commitment')
        data=json.loads(body)
        if not isinstance(data,dict) or set(data)!={str(s) for s in t['seeds']}: raise ValueError('Units')
        if any(not isinstance(v,str) or not 0<len(v.encode())<=self.MAX_UNIT for v in data.values()): raise ValueError('Unit bytes')
        with self.db() as db:
            busy,counts,total,size = self._busy(db)
            if db.execute('SELECT 1 FROM queue WHERE id=?',(t['id'],)).fetchone(): return {'status':'duplicate'}
            if busy and t['tier']=='new' and not self._proof(t,root,proof): return {'status':'puzzle_required'}
            # Hard reservations also apply to bytes: newcomers cannot consume trusted space.
            tier_bytes=db.execute("SELECT coalesce(sum(length(payload)),0) FROM queue WHERE state='QUEUED' AND tier=?",(t['tier'],)).fetchone()[0]
            if counts.get(t['tier'],0)>=self.capacity//2 or size+len(body)>self.byte_capacity or tier_bytes+len(body)>self.byte_capacity//2:
                return {'status':'queue_full'}
            draw=int.from_bytes(hmac.new(self.key,('audit:'+t['id']+root).encode(),hashlib.sha256).digest(),'big')%len(t['seeds'])
            db.execute('INSERT INTO queue VALUES(?,?,?,?,?,?,?,?,?,?)',
                (t['id'],owner,t['tier'],ticket,root,body,json.dumps([t['seeds'][draw]]),'QUEUED',self.clock(),t['expires']))
        return {'status':'queued','id':t['id']}

    def pending(self,tier):
        # Trusted verifier interface; never exposed to submitting clients.
        with self.db() as db:
            self._expire(db)
            r=db.execute("SELECT * FROM queue WHERE state='QUEUED' AND tier=? ORDER BY issued,id LIMIT 1",(tier,)).fetchone()
            return dict(r) if r else None

    def finish(self, identity, verdict, store):
        """Trusted verifier supplies exact committed digest and scientific verdict.

        store(db,row) persists scientific output transactionally before credit;
        the experiment uses a separate immutable output table. No external I/O
        should occur within this callback. Real replay remains an integration.
        """
        root, ok = verdict
        if type(ok)!=bool: raise ValueError('Verdict')
        with self.db() as db:
            self._expire(db)
            r=db.execute("SELECT * FROM queue WHERE id=? AND state='QUEUED'",(identity,)).fetchone()
            if not r or r['root']!=root: raise ValueError('Bound verdict required')
            if ok: store(db,dict(r))
            db.execute('UPDATE queue SET state=?,payload=NULL WHERE id=?',('GRANTED' if ok else 'FAILED',identity))

    def redeem(self, identity, owner):
        with self.db() as db:
            self._expire(db)
            if db.execute("UPDATE queue SET state='REDEEMED' WHERE id=? AND owner=? AND state='GRANTED'",(identity,owner)).rowcount!=1:
                raise ValueError('No credit')


def solve(challenge, bits):
    for n in range(2**64):
        if int.from_bytes(hashlib.sha256(challenge.encode()+n.to_bytes(8,'big')).digest(),'big')<2**(256-bits):
            return {'challenge':challenge,'nonce':n}
