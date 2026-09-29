import hashlib
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from research.screened_admission import ScreenedAdmission, Siteverify
from research.ticket_admission import encoded


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='tmp')
        self.now = [1000.]
        self.c = ScreenedAdmission(Path(self.tmp.name)/'q.sqlite', b'x'*32, {'campaign': 'fixture'},
                                   clock=lambda: self.now[0], verify_screen=lambda token, binding: token.startswith('valid'),
                                   issuance_rate=1000, audit_probability=1)

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, owner, trusted=False):
        t = self.c.issue(owner, trusted=trusted)
        body = encoded({str(s): 'output' for s in t['assignment']['seeds']})
        root = hashlib.sha256(body).hexdigest()
        return self.c.submit(t['ticket'], root, body, owner), t

    def test_bound_validation_and_fail_closed(self):
        r = dict(success=True, hostname='example.org', action='admission', cdata='session-binding',
                 challenge_ts=datetime.fromtimestamp(990, timezone.utc).isoformat())
        verify = Siteverify('test-only', 'example.org', clock=lambda:1000, transport=lambda _:r)
        self.assertTrue(verify('token', 'session-binding'))
        for field, bad in [('hostname','elsewhere'), ('action','other'), ('cdata','other'), ('success',1), ('challenge_ts','bad')]:
            good = r[field]; r[field] = bad
            self.assertFalse(verify('token', 'session-binding')); r[field] = good
        self.assertFalse(verify('x'*2049, 'session-binding'))
        r['challenge_ts'] = datetime.fromtimestamp(600, timezone.utc).isoformat()
        self.assertFalse(verify('token', 'session-binding'))
        def unavailable(_): raise TimeoutError()
        verify.transport = unavailable
        self.assertFalse(verify('token', 'session-binding'))

    def test_allowance_binding_expiry_and_no_topup(self):
        self.assertTrue(self.c.promote('u', 'valid-token'))
        self.assertFalse(self.c.promote('v', 'valid-token'))
        self.assertFalse(self.c.promote('u', 'valid-other'))
        tickets = [self.c.issue('u') for _ in range(4)]
        self.assertEqual([t['assignment']['tier'] for t in tickets], ['provisional']*3+['new'])
        seeds = [s for t in tickets for s in t['assignment']['seeds']]
        self.assertEqual(len(seeds), len(set(seeds)))
        with self.assertRaises(ValueError): self.c._ticket(tickets[0]['ticket'], 'v')
        self.now[0] += 301
        self.assertEqual(self.c.issue('u')['assignment']['tier'], 'new')

    def test_deferred_credit_once_and_revocation(self):
        self.c.promote('u','valid-u')
        r,t = self.send('u')
        self.assertTrue(self.c.redeem(r['id'],'u'))
        self.assertFalse(self.c.redeem(r['id'],'u'))
        second,_ = self.send('u')
        row = self.c.claim('provisional')
        self.c.finish(row['id'], (row['root'], False), lambda *args:self.fail('invalid science stored'))
        self.assertFalse(self.c.redeem(second['id'],'u'))
        self.assertEqual(self.c.issue('u')['status'],'quarantined')
        self.assertFalse(self.c.promote('u','valid-renew'))

    def test_unsampled_storage_bounded_and_trusted_isolated(self):
        self.c.probability = 0
        for i in range(8):
            owner = str(i); self.c.promote(owner,'valid-'+owner)
            r,_ = self.send(owner); self.assertEqual(r['status'],'accepted')
        self.c.promote('extra','valid-extra')
        self.assertEqual(self.send('extra')[0]['status'],'queue_full')
        self.assertEqual(self.send('trusted',True)[0]['status'],'accepted')
        self.assertIsNone(self.c.claim('provisional'))
        with self.c.db() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM queue WHERE state='UNVERIFIED'").fetchone()[0],8)

    def test_mandatory_replay_before_admission_and_storage(self):
        self.c.mode = 'mandatory'; self.c.promote('u','valid-u')
        r,_ = self.send('u')
        self.assertFalse(self.c.redeem(r['id'],'u'))
        row = self.c.claim('provisional'); stored=[]
        self.c.finish(row['id'],(row['root'],True),lambda db,r:stored.append(r['root']))
        self.assertEqual(stored,[row['root']]); self.assertTrue(self.c.redeem(r['id'],'u'))


if __name__ == '__main__': unittest.main()
