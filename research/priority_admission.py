"""Effort-priority newcomer admission on top of the isolated ticket prototype.

NOT the deployed PoolAdmission. A fake submission costs its sender only the
entry puzzle, while rejecting it costs the verifier a full molecular replay, so
under overload the verifier's replay capacity is the scarce resource. Instead of
one fixed puzzle price, newcomers bid for it:

- Under overload a newcomer proves effort as a count of distinct small
  subpuzzle solutions bound to its ticket and output commitment. Many small
  subpuzzles give the same expected cost as one large puzzle with far lower
  variance, so an honest phone's solve time is predictable.
- Newcomer submissions are replayed in decreasing effort, and a full newcomer
  queue evicts its lowest-effort entry for a strictly higher bid.
- The server publishes a suggested effort that rises only while the newcomer
  queue is full and decays with a 10 s half-life afterwards, so honest clients
  pay nothing without pressure.
- Established users keep the prototype's reserved capacity and never bid.

A claimed submission is marked AUDITING, so it cannot be evicted mid-replay and
no longer occupies a queue seat.
"""
import hashlib
import hmac
import json
import math

from research.ticket_admission import TicketAdmission

HALF_LIFE_S = 10


class PriorityAdmission(TicketAdmission):
    MAX_NONCES = 8192

    def __init__(self, path, key, spec, *, sub_bits=10, **kw):
        super().__init__(path, key, spec, puzzle_bits=sub_bits, **kw)
        with self.db() as db:
            if 'effort' not in {r[1] for r in db.execute('PRAGMA table_info(queue)')}:
                db.execute('ALTER TABLE queue ADD COLUMN effort INTEGER NOT NULL DEFAULT 0')
            db.execute('CREATE TABLE IF NOT EXISTS pricing(id INTEGER PRIMARY KEY,suggested REAL,at REAL)')
            db.execute('INSERT OR IGNORE INTO pricing VALUES(1,0,?)', (self.clock(),))

    def _suggested(self, db):
        now = self.clock()
        s, at = db.execute('SELECT suggested,at FROM pricing').fetchone()
        s *= 0.5 ** (max(0.0, now - at) / HALF_LIFE_S)
        low = db.execute("SELECT min(effort),count(*) FROM queue WHERE state='QUEUED' AND tier='new'").fetchone()
        if low[1] >= self.capacity // 2:
            s = max(s, low[0] + 1)  # just enough to evict the weakest bid
        db.execute('UPDATE pricing SET suggested=?,at=?', (s, now))
        return math.ceil(s) if s >= 0.5 else 0

    def offer(self, ticket, root, owner):
        t = self._ticket(ticket, owner)
        if len(root) != 64 or any(c not in '0123456789abcdef' for c in root): raise ValueError('Root')
        with self.db() as db:
            busy = self._busy(db)[0]; suggested = self._suggested(db)
        if t['tier'] == 'trusted' or not busy: return {'status': 'ready'}
        p = dict(purpose='entry', ticket=t['id'], owner=owner, root=root, bits=self.bits,
                 expires=min(t['expires'], self.clock() + 60))
        return {'status': 'effort', 'challenge': self.seal(p), 'sub_bits': self.bits, 'suggested': suggested}

    def effort_of(self, t, root, proof):
        """Number of subpuzzles proven, or 0. One bad nonce voids the proof, so a
        proof cannot be padded, and verification is bounded by MAX_NONCES hashes."""
        if proof is None or not isinstance(proof, dict) or set(proof) != {'challenge', 'nonces'}: return 0
        try:
            p = self.open(proof['challenge'], 'entry')
        except (ValueError, KeyError, TypeError):
            return 0
        if (p.get('ticket'), p.get('owner'), p.get('root'), p.get('bits')) != (t['id'], t['owner'], root, self.bits): return 0
        nonces = proof['nonces']
        if not isinstance(nonces, list) or not 0 < len(nonces) <= self.MAX_NONCES or len(set(nonces)) != len(nonces): return 0
        if any(type(n) != int or not 0 <= n < 2**64 for n in nonces): return 0
        target = 2 ** (256 - self.bits); c = proof['challenge'].encode()
        for n in nonces:
            if int.from_bytes(hashlib.sha256(c + n.to_bytes(8, 'big')).digest(), 'big') >= target: return 0
        return len(nonces)

    def submit(self, ticket, root, body, owner, proof=None):
        if not isinstance(body, bytes) or len(body) > self.MAX_BODY: return {'status': 'too_large'}
        t = self._ticket(ticket, owner)
        if hashlib.sha256(body).hexdigest() != root: raise ValueError('Commitment')
        data = json.loads(body)
        if not isinstance(data, dict) or set(data) != {str(s) for s in t['seeds']}: raise ValueError('Units')
        if any(not isinstance(v, str) or not 0 < len(v.encode()) <= self.MAX_UNIT for v in data.values()): raise ValueError('Unit bytes')
        effort = self.effort_of(t, root, proof)
        with self.db() as db:
            busy, counts, total, size = self._busy(db)
            if db.execute('SELECT 1 FROM queue WHERE id=?', (t['id'],)).fetchone(): return {'status': 'duplicate'}
            tier = t['tier']; evict = None; freed = 0
            if counts.get(tier, 0) >= self.capacity // 2:
                if tier != 'new': return {'status': 'queue_full'}
                low = db.execute("SELECT id,effort,length(payload) b FROM queue WHERE state='QUEUED' AND tier='new' "
                                 "ORDER BY effort,issued DESC,id LIMIT 1").fetchone()
                if effort <= low['effort']: return {'status': 'queue_full', 'suggested': self._suggested(db)}
                evict, freed = low['id'], low['b']
            tier_bytes = db.execute("SELECT coalesce(sum(length(payload)),0) FROM queue WHERE state='QUEUED' AND tier=?", (tier,)).fetchone()[0]
            if size - freed + len(body) > self.byte_capacity or tier_bytes - freed + len(body) > self.byte_capacity // 2:
                return {'status': 'queue_full'}
            if evict: db.execute("UPDATE queue SET state='EVICTED',payload=NULL WHERE id=?", (evict,))
            draw = int.from_bytes(hmac.new(self.key, ('audit:' + t['id'] + root).encode(), hashlib.sha256).digest(), 'big') % len(t['seeds'])
            db.execute('INSERT INTO queue(id,owner,tier,ticket,root,payload,draws,state,issued,expires,effort) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (t['id'], owner, tier, ticket, root, body, json.dumps([t['seeds'][draw]]), 'QUEUED', self.clock(), t['expires'], effort))
            self._suggested(db)
        return {'status': 'queued', 'id': t['id'], 'effort': effort, 'evicted_other': evict is not None}

    def claim(self, tier):
        """Trusted verifier: take the next submission for replay. Newcomers are
        served highest effort first; established users first come, first served."""
        order = 'effort DESC,issued,id' if tier == 'new' else 'issued,id'
        with self.db() as db:
            self._expire(db)
            r = db.execute(f"SELECT * FROM queue WHERE state='QUEUED' AND tier=? ORDER BY {order} LIMIT 1", (tier,)).fetchone()
            if not r: return None
            db.execute("UPDATE queue SET state='AUDITING' WHERE id=?", (r['id'],))
            return dict(r)

    def finish(self, identity, verdict, store):
        root, ok = verdict
        if type(ok) != bool: raise ValueError('Verdict')
        with self.db() as db:
            self._expire(db)
            r = db.execute("SELECT * FROM queue WHERE id=? AND state='AUDITING'", (identity,)).fetchone()
            if not r or r['root'] != root: raise ValueError('Bound verdict required')
            if ok: store(db, dict(r))
            db.execute('UPDATE queue SET state=?,payload=NULL WHERE id=?', ('GRANTED' if ok else 'FAILED', identity))

    def state(self, identity):
        with self.db() as db:
            r = db.execute('SELECT state FROM queue WHERE id=?', (identity,)).fetchone()
            return r['state'] if r else None


def solve_effort(challenge, bits, n):
    """Honest client: n distinct nonces each below the subpuzzle target."""
    target = 2 ** (256 - bits); c = challenge.encode(); out = []; nonce = 0
    while len(out) < n:
        if int.from_bytes(hashlib.sha256(c + nonce.to_bytes(8, 'big')).digest(), 'big') < target: out.append(nonce)
        nonce += 1
    return {'challenge': challenge, 'nonces': out}
