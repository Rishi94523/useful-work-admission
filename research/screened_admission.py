"""Isolated amendment-20 prototype; not wired into the deployed campaign.

Reuse signed tickets, one global seed allocator and transactional ledger. External
screening confers bounded provisional access, never device uniqueness or earned
trust. The host supplies authenticated session IDs and trusted replay verdicts.
Unverified payloads stay out of scientific storage, including unsampled outputs.
"""
import hashlib
import hmac
import json
import secrets
import time
import urllib.request
from datetime import datetime

from research.ticket_admission import TicketAdmission


class Siteverify:
    def __init__(self, secret, hostname, action='admission', *, clock=time.time, transport=None):
        if not secret or not hostname:
            raise ValueError('Siteverify configuration required')
        self.secret, self.hostname, self.action = secret, hostname, action
        self.clock, self.transport = clock, transport or self._post

    @staticmethod
    def _post(fields):
        req = urllib.request.Request('https://challenges.cloudflare.com/turnstile/v0/siteverify',
                                     data=json.dumps(fields).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read(16385)
        if len(raw) > 16384:
            raise ValueError('Oversized Siteverify response')
        return json.loads(raw)

    def __call__(self, token, binding):
        if not isinstance(token, str) or not 1 <= len(token) <= 2048:
            return False
        try:
            r = self.transport({'secret': self.secret, 'response': token})
            stamp = datetime.fromisoformat(r['challenge_ts'].replace('Z', '+00:00')).timestamp()
            return (r.get('success') is True and r.get('hostname') == self.hostname
                    and r.get('action') == self.action and r.get('cdata') == binding
                    and 0 <= self.clock() - stamp <= 300)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return False


class ScreenedAdmission(TicketAdmission):
    LANES = ('new', 'provisional', 'trusted')

    def __init__(self, *args, verify_screen, mode='deferred', audit_probability=.1, **kw):
        if mode not in ('none', 'screen_only', 'mandatory', 'deferred') or not 0 <= audit_probability <= 1:
            raise ValueError('Policy')
        super().__init__(*args, **kw)
        self.verify_screen, self.mode, self.probability = verify_screen, mode, audit_probability
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS screen_grants(owner TEXT PRIMARY KEY,remaining INTEGER,until REAL,revoked INTEGER);
            CREATE TABLE IF NOT EXISTS screen_spent(token TEXT PRIMARY KEY,until REAL);
            CREATE INDEX IF NOT EXISTS screen_spent_expiry ON screen_spent(until);
            CREATE INDEX IF NOT EXISTS screen_queue_expiry ON queue(expires);
            CREATE INDEX IF NOT EXISTS screen_queue_retained ON queue(tier) WHERE payload IS NOT NULL;
            CREATE TABLE IF NOT EXISTS screen_credits(id TEXT PRIMARY KEY,owner TEXT,state TEXT);
            ''')
            for lane in ('provisional', 'screen_calls'):
                db.execute('INSERT OR IGNORE INTO budget VALUES(?,32,?)', (lane, self.clock()))

    def binding(self, owner):
        return hmac.new(self.key, ('screen-session:' + owner).encode(), hashlib.sha256).hexdigest()

    def _budget(self, db, lane):
        row = db.execute('SELECT * FROM budget WHERE tier=?', (lane,)).fetchone()
        n = min(32, row['tokens'] + max(0, self.clock() - row['at']) * self.issuance_rate)
        db.execute('UPDATE budget SET tokens=?,at=? WHERE tier=?', (max(0, n-1) if n >= 1 else n, self.clock(), lane))
        return n >= 1

    def promote(self, owner, token):
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ValueError('Session')
        if not isinstance(token, str) or not 1 <= len(token) <= 2048:
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.db() as db:
            db.execute('DELETE FROM screen_spent WHERE until<=?', (self.clock(),))
            prior = db.execute('SELECT * FROM screen_grants WHERE owner=?', (owner,)).fetchone()
            if prior and (prior['revoked'] or prior['until'] > self.clock()):
                return False  # no replenishing an active or exhausted allowance
            if not self._budget(db, 'screen_calls'):
                return False
            if db.execute('INSERT OR IGNORE INTO screen_spent VALUES(?,?)', (digest, self.clock()+300)).rowcount != 1:
                return False
        if not self.verify_screen(token, self.binding(owner)):
            return False
        with self.db() as db:
            prior = db.execute('SELECT * FROM screen_grants WHERE owner=?', (owner,)).fetchone()
            if prior and (prior['revoked'] or prior['until'] > self.clock()):
                return False
            db.execute('INSERT OR REPLACE INTO screen_grants VALUES(?,?,?,0)', (owner, 3, self.clock()+300))
        return True

    def issue(self, owner, *, trusted=False):
        # trusted is server-owned, never accepted from request JSON.
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128:
            raise ValueError('Session')
        with self.db() as db:
            grant = db.execute('SELECT * FROM screen_grants WHERE owner=?', (owner,)).fetchone()
            if grant and grant['revoked']:
                return {'status': 'quarantined'}
            low = self.mode != 'none' and grant and grant['remaining'] > 0 and grant['until'] > self.clock()
            lane = 'trusted' if trusted else 'provisional' if low else 'new'
            if not self._budget(db, lane):
                return {'status': 'rate_limited'}
            start = db.execute('SELECT next_seed FROM counters').fetchone()[0]
            n = 4 if lane == 'new' else 1
            if start+n >= 2**30:
                return {'status': 'seed_space_exhausted'}
            db.execute('UPDATE counters SET next_seed=?', (start+n,))
            if lane == 'provisional':
                db.execute('UPDATE screen_grants SET remaining=remaining-1 WHERE owner=?', (owner,))
        d = dict(purpose='work', id=secrets.token_hex(16), owner=owner, tier=lane,
                 spec=self.spec_hash, seeds=list(range(start, start+n)), issued=self.clock(), expires=self.clock()+self.ttl)
        return {'status': 'ticket', 'ticket': self.seal(d), 'assignment': d, 'inputs': self.spec}

    def submit(self, ticket, root, body, owner, proof=None):
        if not isinstance(body, bytes) or len(body) > self.MAX_BODY:
            return {'status': 'too_large'}
        t = self._ticket(ticket, owner)
        if hashlib.sha256(body).hexdigest() != root:
            raise ValueError('Commitment')
        data = json.loads(body)
        if not isinstance(data, dict) or set(data) != {str(s) for s in t['seeds']}:
            raise ValueError('Units')
        if any(not isinstance(v, str) or not 0 < len(v.encode()) <= self.MAX_UNIT for v in data.values()):
            raise ValueError('Unit bytes')
        with self.db() as db:
            self._expire(db)
            grant = db.execute('SELECT revoked FROM screen_grants WHERE owner=?', (owner,)).fetchone()
            if grant and grant[0]:
                return {'status': 'quarantined'}
            if db.execute('SELECT 1 FROM queue WHERE id=?', (t['id'],)).fetchone():
                return {'status': 'duplicate'}
            lane = t['tier']
            count, size = db.execute("SELECT count(*),coalesce(sum(length(payload)),0) FROM queue WHERE tier=? AND payload IS NOT NULL", (lane,)).fetchone()
            if count >= self.capacity//2 or size+len(body) > self.byte_capacity//2:
                return {'status': 'queue_full'}
            sample = int.from_bytes(hmac.new(self.key, ('sample:'+t['id']+root).encode(), hashlib.sha256).digest(), 'big') / 2**256
            draw = int.from_bytes(hmac.new(self.key, ('unit:'+t['id']+root).encode(), hashlib.sha256).digest(), 'big') % len(t['seeds'])
            screened = lane == 'provisional'
            deferred = screened and self.mode in ('deferred', 'screen_only')
            selected = not deferred or (self.mode == 'deferred' and sample < self.probability)
            state = 'QUEUED' if selected else 'UNVERIFIED'
            # Screening-only does no scientific collection; its fixture is discarded.
            payload = None if screened and self.mode == 'screen_only' else body
            db.execute('INSERT INTO queue VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (t['id'], owner, lane, ticket, root, payload, json.dumps([t['seeds'][draw]]), state, self.clock(), t['expires']))
            db.execute('INSERT INTO screen_credits VALUES(?,?,?)', (t['id'], owner, 'GRANTED' if deferred else 'WAITING'))
        # Never reveal the audit selection before the complete committed upload.
        return {'status': 'accepted', 'id': t['id']}

    def claim(self, lane):
        with self.db() as db:
            self._expire(db)
            row = db.execute("SELECT * FROM queue WHERE state='QUEUED' AND tier=? ORDER BY issued,id LIMIT 1", (lane,)).fetchone()
            if row:
                db.execute("UPDATE queue SET state='AUDITING' WHERE id=?", (row['id'],))
            return dict(row) if row else None

    def finish(self, identity, verdict, store):
        root, ok = verdict
        if type(ok) is not bool:
            raise ValueError('Verdict')
        with self.db() as db:
            row = db.execute("SELECT * FROM queue WHERE id=? AND state='AUDITING'", (identity,)).fetchone()
            if not row or row['root'] != root:
                raise ValueError('Bound verdict required')
            if ok:
                store(db, dict(row))
                db.execute("UPDATE screen_credits SET state='GRANTED' WHERE id=? AND state='WAITING'", (identity,))
            else:
                db.execute('INSERT OR REPLACE INTO screen_grants VALUES(?,0,?,1)', (row['owner'], self.clock()))
                db.execute("UPDATE screen_credits SET state='REVOKED' WHERE owner=? AND state!='REDEEMED'", (row['owner'],))
                db.execute("UPDATE queue SET state='QUARANTINED',payload=NULL WHERE owner=?", (row['owner'],))
            db.execute('UPDATE queue SET state=?,payload=NULL WHERE id=?', ('VERIFIED' if ok else 'FAILED', identity))

    def redeem(self, identity, owner):
        with self.db() as db:
            if db.execute('SELECT 1 FROM queue WHERE id=? AND expires>?', (identity, self.clock())).fetchone() is None:
                return False
            return db.execute("UPDATE screen_credits SET state='REDEEMED' WHERE id=? AND owner=? AND state='GRANTED'", (identity, owner)).rowcount == 1
