from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from research.docking_campaign import Campaign


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=100.;self.c=Campaign(Path(self.temp.name)/'state.db',lambda:self.now)
    def add(self,ligand='a',start=0):
        return self.c.add('pilot',{'model_version':'grid-v1','receptor':'rec-sha','ligand':ligand,'conformer_bank':'bank-sha','region':'pocket','search_parameters':{'stride':5}},start,64,1.)
    def complete(self,lease,accepted=True):
        h='a'*64;ch=self.c.commit(lease['lease'],'owner',lease['binding'],h)
        return self.c.finish(lease['lease'],'owner',lease['binding'],ch['id'],h,accepted,{'kind':'statistical_audit'})
    def test_completed_never_reassigned(self):
        self.add();lease=self.c.lease('pilot','owner');self.complete(lease)
        self.now+=1000
        with self.assertRaises(LookupError):self.c.lease('pilot','owner')
        self.assertEqual(self.c.snapshot()['units'],{'COMPLETED':1})
    def test_overlap_and_campaign_rename_cannot_duplicate(self):
        self.add()
        with self.assertRaises(ValueError):self.add(start=32)
        spec={'model_version':'grid-v1','receptor':'rec-sha','ligand':'a','conformer_bank':'bank-sha','region':'pocket','search_parameters':{'stride':5}}
        with self.assertRaises(ValueError):self.c.add('renamed',spec,0,64,1.)
        self.add(start=64)
    def test_expiry_reassigns_only_uncompleted_work(self):
        task=self.add();old=self.c.lease('pilot','owner',ttl=1);self.now+=2
        new=self.c.lease('pilot','owner');self.assertNotEqual(old['lease'],new['lease']);self.assertEqual(new['tasks'][0]['task'],task)
        with self.assertRaises(ValueError):self.c.commit(old['lease'],'owner',old['binding'],'b'*64)
        self.complete(new)
    def test_replay_wrong_owner_binding_and_challenge_rejected(self):
        self.add();lease=self.c.lease('pilot','owner');args=(lease['lease'],'owner',lease['binding'])
        with self.assertRaises(ValueError):self.c.commit(lease['lease'],'impostor',lease['binding'],'a'*64)
        with self.assertRaises(ValueError):self.c.commit(lease['lease'],'owner','wrong','a'*64)
        ch=self.c.commit(*args,'a'*64)
        with self.assertRaises(ValueError):self.c.commit(*args,'b'*64)
        with self.assertRaises(ValueError):self.c.finish(*args,'wrong','a'*64,True,{})
        self.c.finish(*args,ch['id'],'a'*64,True,{})
        with self.assertRaises(ValueError):self.c.finish(*args,ch['id'],'a'*64,True,{})
    def test_concurrent_leases_disjoint(self):
        for i in range(32):self.add(str(i))
        with ThreadPoolExecutor(max_workers=16) as pool:
            leases=list(pool.map(lambda _:self.c.lease('pilot','owner',jobs=2),range(16)))
        tasks=[t['task'] for lease in leases for t in lease['tasks']]
        self.assertEqual(len(set(tasks)),32)
    def test_duplicate_completion_race_one_credit(self):
        self.add();lease=self.c.lease('pilot','owner');args=(lease['lease'],'owner',lease['binding']);ch=self.c.commit(*args,'a'*64)
        def finish(_):
            try:return self.c.finish(*args,ch['id'],'a'*64,True,{})
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(finish,range(16)))
        self.assertEqual(sum(results),1)
    def test_failed_bundle_does_not_consume_available_unit(self):
        self.add()
        with self.assertRaises(LookupError):self.c.lease('pilot','owner',jobs=4)
        self.assertEqual(self.c.snapshot()['units'],{'UNASSIGNED':1})
    def test_late_verification_cannot_credit(self):
        self.add();lease=self.c.lease('pilot','owner',ttl=1);args=(lease['lease'],'owner',lease['binding']);ch=self.c.commit(*args,'a'*64);self.now+=2
        with self.assertRaises(ValueError):self.c.finish(*args,ch['id'],'a'*64,True,{})
        self.assertEqual(self.c.snapshot()['units'],{'EXPIRED':1})


if __name__=='__main__':unittest.main()
