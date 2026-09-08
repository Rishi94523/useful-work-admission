import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from research.adaptive_admission import AdaptiveAdmission


def populate(c, cohorts=4):
    for ligand in range(16):
        for cohort in range(cohorts):
            c.register('test','engine','maps',str(ligand),'input-'+str(ligand),'box',16*cohort,16,16000,16)


class AdaptiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='tmp');self.now=[0]
        self.c=AdaptiveAdmission(Path(self.tmp.name)/'c.sqlite',clock=lambda:self.now[0]);populate(self.c)
    def tearDown(self):self.tmp.cleanup()
    def complete(self, lease, accepted, owner='a'):
        ch=self.c.commit(lease['lease'],owner,lease['binding'],'a'*64)
        return self.c.finish(lease['lease'],owner,lease['binding'],ch['id'],'a'*64,accepted,{})
    def test_honest_stays_low_and_work_consumed_once(self):
        seen=set()
        for _ in range(8):
            r=self.c.request('test','a');self.assertEqual(r['tier'],'low');self.assertEqual(r['risk'],0)
            self.assertNotIn(r['tasks'][0]['task'],seen);seen.add(r['tasks'][0]['task'])
            self.assertEqual(self.complete(r,True)['risk'],0);self.now[0]+=60
        with self.assertRaises(ValueError):self.complete(r,True)
    def test_failures_raise_work_then_cooldown(self):
        sizes=[]
        for _ in range(3):
            r=self.c.request('test','a');sizes.append(len(self.c.units(r)));self.complete(r,False);self.now[0]+=.1
        self.assertEqual(sizes,[16,64,256]);self.assertEqual(self.c.request('test','a')['status'],'cooldown')
    def test_abandonment_counted_once_and_errors_recover(self):
        r=self.c.request('test','a');self.now[0]=121
        self.assertEqual(self.c.risk_state('a')['score'],8)
        self.assertEqual(self.c.risk_state('a')['score'],8)
        r=self.c.request('test','a');self.assertEqual(r['tier'],'low');self.complete(r,True)
        self.now[0]+=1200;self.assertEqual(self.c.risk_state('a')['score'],0)
    def test_committed_abandonment_and_policy_tamper(self):
        r=self.c.request('test','a')
        with self.assertRaises(ValueError):self.c.commit(r['lease'],'a',r['binding'],'a'*64,samples=1)
        self.c.commit(r['lease'],'a',r['binding'],'a'*64);self.now[0]=121
        self.assertEqual(self.c.risk_state('a')['score'],12)
        with self.assertRaises(ValueError):self.c.lease('test','a')
    def test_concurrent_same_identity_only_one_lease(self):
        with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(lambda _:self.c.request('test','a'),range(4)))
        self.assertEqual(sum(r['status']=='assigned' for r in rows),1)
    def test_partial_bucket_refill_survives_denied_requests(self):
        for i in range(32):self.c.request('missing','id'+str(i))
        self.now[0]=.2;self.assertEqual(self.c.request('missing','next')['reason'],'global-rate-budget')
        self.now[0]=.5;self.assertEqual(self.c.request('missing','next')['reason'],'scientific-pool')
    def test_risk_persists_across_restart(self):
        self.complete(self.c.request('test','a'),False)
        other=AdaptiveAdmission(self.c.path,clock=lambda:self.now[0])
        self.assertEqual(other.request('test','a')['tier'],'medium')

if __name__=='__main__':unittest.main()
