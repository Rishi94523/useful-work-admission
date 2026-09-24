import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research.ticket_admission import TicketAdmission, encoded, solve


class TicketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.now=[0.]
        self.c=TicketAdmission(Path(self.tmp.name)/'db.sqlite',b'x'*32,
            {'campaign':'test','inputs':'fixed','max_evals':256000},clock=lambda:self.now[0],puzzle_bits=4)
    def tearDown(self):self.tmp.cleanup()
    def ticket(self,owner='a',trusted=False):return self.c.issue(owner,trusted=trusted)
    def payload(self,t):
        b=encoded({str(s):'fixture' for s in t['assignment']['seeds']})
        return hashlib.sha256(b).hexdigest(),b
    def put(self,t,owner='a',proof=None):
        root,body=self.payload(t);return self.c.submit(t['ticket'],root,body,owner,proof)
    def fill(self):
        for i in range(8):self.assertEqual(self.put(self.ticket('a'+str(i)),'a'+str(i))['status'],'queued')
    def test_idle_tickets_allocate_unique_work_without_seats(self):
        seeds=[]
        for i in range(24):seeds+=self.ticket(str(i))['assignment']['seeds']
        self.assertEqual(len(seeds),len(set(seeds)))
        with self.c.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM queue').fetchone()[0],0)
    def test_ticket_session_mac_and_expiry(self):
        t=self.ticket();root,body=self.payload(t)
        with self.assertRaises(ValueError):self.c.submit(t['ticket'],root,body,'other')
        with self.assertRaises(ValueError):self.c.submit(t['ticket']+'0',root,body,'a')
        self.now[0]=120
        with self.assertRaises(ValueError):self.put(t)
    def test_input_and_commitment_binding(self):
        t=self.ticket();root,body=self.payload(t)
        with self.assertRaises(ValueError):self.c.submit(t['ticket'],'0'*64,body,'a')
        body=encoded({'unexpected-seed':'fixture'})
        with self.assertRaises(ValueError):self.c.submit(t['ticket'],hashlib.sha256(body).hexdigest(),body,'a')
    def test_overload_requires_actual_bound_puzzle_and_reserves_trusted(self):
        self.fill();t=self.ticket('new');root,body=self.payload(t)
        self.assertEqual(self.put(t,'new')['status'],'puzzle_required')
        p=self.c.offer(t['ticket'],root,'new');proof=solve(p['challenge'],p['bits'])
        self.assertEqual(self.put(t,'new',proof)['status'],'queue_full')
        row=self.c.pending('new');self.c.finish(row['id'],(row['root'],False),lambda *a:None)
        self.assertEqual(self.put(t,'new',proof)['status'],'queued')
        self.assertEqual(self.put(t,'new',proof)['status'],'duplicate')
        other=self.ticket('other');self.assertEqual(self.put(other,'other',proof)['status'],'puzzle_required')
        trusted=self.ticket('trusted',True);self.assertEqual(self.put(trusted,'trusted')['status'],'queued')
    def test_bytes_are_bounded_and_no_audit_draw_disclosed(self):
        t=self.ticket();r=self.put(t);self.assertEqual(set(r),{'status','id'})
        self.assertEqual(self.c.submit(t['ticket'],'0'*64,b'x'*(self.c.MAX_BODY+1),'a')['status'],'too_large')
        t=self.ticket('b');body=encoded({str(s):'x'*(self.c.MAX_UNIT+1) for s in t['assignment']['seeds']})
        with self.assertRaises(ValueError):self.c.submit(t['ticket'],hashlib.sha256(body).hexdigest(),body,'b')
    def test_duplicate_concurrent_submission_and_one_use_credit(self):
        t=self.ticket()
        with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(lambda _:self.put(t),range(4)))
        self.assertEqual(sum(x['status']=='queued' for x in r),1)
        row=self.c.pending('new')
        with self.assertRaises(ValueError):self.c.finish(row['id'],('0'*64,True),lambda *a:None)
        self.c.finish(row['id'],(row['root'],True),lambda db,r:db.execute('CREATE TABLE science(x INTEGER)'))
        self.c.redeem(row['id'],'a')
        with self.assertRaises(ValueError):self.c.redeem(row['id'],'a')
        self.assertEqual(self.put(t)['status'],'duplicate')
    def test_expired_receipts_cannot_replay_and_seed_counter_survives_restart(self):
        t=self.ticket();self.put(t);self.now[0]=121;self.assertIsNone(self.c.pending('new'))
        with self.assertRaises(ValueError):self.put(t)
        self.c=TicketAdmission(self.c.path,b'x'*32,self.c.spec,clock=lambda:self.now[0],puzzle_bits=4)
        self.assertGreater(min(self.ticket()['assignment']['seeds']),max(t['assignment']['seeds']))
    def test_failed_science_store_rolls_back_credit(self):
        t=self.ticket();self.put(t);r=self.c.pending('new')
        def fail(db,row):raise RuntimeError('storage failed')
        with self.assertRaises(RuntimeError):self.c.finish(r['id'],(r['root'],True),fail)
        self.assertIsNotNone(self.c.pending('new'))
        with self.assertRaises(ValueError):self.c.redeem(r['id'],'a')
    def test_aggregate_byte_budget_and_trusted_reservation(self):
        self.c.byte_capacity=200
        self.assertEqual(self.put(self.ticket())['status'],'queued')
        self.assertEqual(self.put(self.ticket('b'),'b')['status'],'queue_full')
        self.assertEqual(self.put(self.ticket('trusted',True),'trusted')['status'],'queued')
    def test_expired_or_altered_puzzle_does_not_open_queue(self):
        self.fill();t=self.ticket('new');root,body=self.payload(t)
        p=self.c.offer(t['ticket'],root,'new');proof=solve(p['challenge'],p['bits'])
        row=self.c.pending('new');self.c.finish(row['id'],(row['root'],False),lambda *a:None)
        bad={**proof,'challenge':proof['challenge']+'0'}
        self.assertEqual(self.put(t,'new',bad)['status'],'puzzle_required')
        self.now[0]=31
        # Keep overload active to test expiry independently of the grace period.
        with self.c.db() as db:db.execute('UPDATE control SET overload_until=100')
        self.assertEqual(self.put(t,'new',proof)['status'],'puzzle_required')


if __name__=='__main__':unittest.main()
