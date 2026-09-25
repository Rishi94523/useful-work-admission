"""Attested-newcomer lane on top of effort-priority admission (amendment 10).

NOT the deployed PoolAdmission. A newcomer presenting a device-attestation
token gets an attested ticket: no puzzle, its own seat and byte reservation,
and first-come first-served replay with strict priority over anonymous
newcomers. Anonymous newcomers keep the effort-bidding lane; established users
keep their reserved lane.

The token is modelled on Privacy Pass rate-limited tokens (Apple's Private
Access Tokens): an issuer attests a genuine device, caps tokens per device per
origin, and the origin sees an unlinkable, single-use, origin-bound token. The
origin checks a token through `verify_attestation(token) -> nullifier or None`
and stores the nullifier so it cannot be spent twice. The blind-signature
cryptography is not implemented; MockAttester stands in for the issuer. Tokens
are unlinkable, so a device whose output fails audit cannot be penalised; only
the issuer's per-device limit bounds abuse.
"""
import hashlib
import hmac
import json
import secrets

from research.priority_admission import PriorityAdmission

TIERS = ('new', 'attested', 'trusted')


class AttestedAdmission(PriorityAdmission):
    def __init__(self, path, key, spec, *, verify_attestation, **kw):
        super().__init__(path, key, spec, **kw)
        self.verify_attestation = verify_attestation
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS spent(nullifier TEXT PRIMARY KEY,at REAL)')
            db.execute('INSERT OR IGNORE INTO budget VALUES(?,32,?)', ('attested', self.clock()))

    def issue(self, owner, *, trusted=False, attestation=None):
        # trusted comes from an authenticated server integration, never JSON input.
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128: raise ValueError('Session')
        nullifier = None
        if not trusted and attestation is not None:
            nullifier = self.verify_attestation(attestation)
            if not isinstance(nullifier, str) or not nullifier: return {'status': 'attestation_invalid'}
        tier = 'trusted' if trusted else 'attested' if nullifier else 'new'
        n = 1 if trusted else 4; now = self.clock()
        with self.db() as db:
            b = db.execute('SELECT * FROM budget WHERE tier=?', (tier,)).fetchone()
            tokens = min(32, b['tokens'] + max(0, now - b['at']) * self.issuance_rate)
            db.execute('UPDATE budget SET tokens=?,at=? WHERE tier=?', (tokens - 1 if tokens >= 1 else tokens, now, tier))
            if tokens < 1: return {'status': 'rate_limited'}  # the attestation is not spent
            if nullifier and db.execute('INSERT OR IGNORE INTO spent VALUES(?,?)', (nullifier, now)).rowcount != 1:
                return {'status': 'attestation_spent'}
            start = db.execute('SELECT next_seed FROM counters').fetchone()[0]
            if start + n >= 2**30: return {'status': 'seed_space_exhausted'}
            db.execute('UPDATE counters SET next_seed=?', (start + n,))
        d = dict(purpose='work', id=secrets.token_hex(16), owner=owner, tier=tier,
                 spec=self.spec_hash, seeds=list(range(start, start + n)), issued=now, expires=now + self.ttl)
        return {'status': 'ticket', 'ticket': self.seal(d), 'assignment': d, 'inputs': self.spec}

    def _busy(self, db):
        """As the prototype, but the attested lane has its own reservations: its
        rows neither trigger overload pricing for anonymous newcomers nor count
        against the shared byte capacity."""
        self._expire(db)
        rows = db.execute("SELECT tier,count(*) n,coalesce(sum(length(payload)),0) b FROM queue WHERE state='QUEUED' GROUP BY tier").fetchall()
        shared = [r for r in rows if r['tier'] != 'attested']
        total = sum(r['n'] for r in shared); size = sum(r['b'] for r in shared)
        if total >= self.capacity // 2 or size >= self.byte_capacity // 2:
            db.execute('UPDATE control SET overload_until=?', (self.clock() + 5,))
        active = db.execute('SELECT overload_until FROM control').fetchone()[0] > self.clock()
        return active, {r['tier']: r['n'] for r in rows}, total, size

    def offer(self, ticket, root, owner):
        t = self._ticket(ticket, owner)
        if t['tier'] == 'attested':
            if len(root) != 64 or any(c not in '0123456789abcdef' for c in root): raise ValueError('Root')
            return {'status': 'ready'}
        return super().offer(ticket, root, owner)

    def submit(self, ticket, root, body, owner, proof=None):
        t = self._ticket(ticket, owner)
        if t['tier'] != 'attested': return super().submit(ticket, root, body, owner, proof)
        # Same commitment and unit checks; never evicts, never bids.
        if not isinstance(body, bytes) or len(body) > self.MAX_BODY: return {'status': 'too_large'}
        if hashlib.sha256(body).hexdigest() != root: raise ValueError('Commitment')
        data = json.loads(body)
        if not isinstance(data, dict) or set(data) != {str(s) for s in t['seeds']}: raise ValueError('Units')
        if any(not isinstance(v, str) or not 0 < len(v.encode()) <= self.MAX_UNIT for v in data.values()): raise ValueError('Unit bytes')
        with self.db() as db:
            _, counts, _, _ = self._busy(db)
            if db.execute('SELECT 1 FROM queue WHERE id=?', (t['id'],)).fetchone(): return {'status': 'duplicate'}
            lane_bytes = db.execute("SELECT coalesce(sum(length(payload)),0) FROM queue WHERE state='QUEUED' AND tier='attested'").fetchone()[0]
            if counts.get('attested', 0) >= self.capacity // 2 or lane_bytes + len(body) > self.byte_capacity // 2:
                return {'status': 'queue_full'}
            draw = int.from_bytes(hmac.new(self.key, ('audit:' + t['id'] + root).encode(), hashlib.sha256).digest(), 'big') % len(t['seeds'])
            db.execute('INSERT INTO queue(id,owner,tier,ticket,root,payload,draws,state,issued,expires,effort) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                       (t['id'], owner, 'attested', ticket, root, body, json.dumps([t['seeds'][draw]]), 'QUEUED', self.clock(), t['expires'], 0))
        return {'status': 'queued', 'id': t['id'], 'effort': 0, 'evicted_other': False}

    def next_newcomer(self):
        """Trusted verifier: attested submissions first, then anonymous by effort."""
        return self.claim('attested') or self.claim('new')


class MockAttester:
    """Stand-in for a rate-limited token issuer. Only the issuer knows devices;
    tokens carry a random nonce and the origin, nothing identifying."""

    def __init__(self, origin, *, per_device, window_s, clock):
        self.origin, self.per_device, self.window_s, self.clock = origin, per_device, window_s, clock
        self._key = secrets.token_bytes(32); self._used = {}

    def token(self, device):
        window = int(self.clock() // self.window_s); k = (device, window)
        if self._used.get(k, 0) >= self.per_device: return None
        self._used[k] = self._used.get(k, 0) + 1
        body = json.dumps({'origin': self.origin, 'nonce': secrets.token_hex(16)}, sort_keys=True)
        return body + '.' + hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()

    def verify(self, token):
        """Returns the token's nullifier, or None. Publicly verifiable in the
        real protocol; keyed here only because the mock has no blind RSA."""
        if not isinstance(token, str) or len(token) > 1024 or '.' not in token: return None
        body, tag = token.rsplit('.', 1)
        if not hmac.compare_digest(tag, hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()): return None
        try:
            d = json.loads(body)
        except ValueError:
            return None
        if not isinstance(d, dict) or d.get('origin') != self.origin: return None
        return hashlib.sha256(body.encode()).hexdigest()
