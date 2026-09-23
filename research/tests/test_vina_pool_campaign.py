import hashlib,tempfile,unittest
from unittest import mock
from pathlib import Path
import research.vina_pool_campaign as rs
from research.vina_pool_campaign import VinaPoolCampaign
class PoolTests(unittest.TestCase):
 def test_multiple_ligand_pools_are_leased_atomically(self):
  with tempfile.TemporaryDirectory(dir='tmp') as d:
   c=VinaPoolCampaign(Path(d)/'p.sqlite',clock=lambda:0)
   spec={'model_version':'e','receptor':'r','ligand':'a','conformer_bank':'input-a','region':'b','search_parameters':{'max_evals':0}}
   c.register_pool('a',spec,[1,2]);c.register_pool('b',dict(spec,ligand='b',conformer_bank='input-b'),[1,2])
   with self.assertRaises(LookupError):c.lease_many(['a','missing'],'x',2)
   self.assertEqual(c.snapshot()['units'],{'UNASSIGNED':4})
   c.register_pool('alias',spec,[1,2])
   with self.assertRaises(ValueError):c.lease_many(['a','alias'],'x',2)
   lease=c.lease_many(['a','b'],'x',2);self.assertEqual(len(lease['tasks']),4)
   ch=c.commit(lease['lease'],'x',lease['binding'],'a'*64,samples=2)
   ids=[t['task'] for t in lease['tasks']];verified=[ids[j] for j,_ in ch['draws']]
   c.finish_outputs(lease['lease'],'x',lease['binding'],ch['id'],'a'*64,{task:b'fixture' for task in ids},verified)
   self.assertTrue(c.coverage('a')['aggregate_ready_provisional']);self.assertTrue(c.coverage('b')['aggregate_ready_provisional'])
   self.assertEqual(c.coverage('a')['replay_verified']+c.coverage('b')['replay_verified'],2)
 def test_many_visitors_durable_coverage_and_no_duplicate_credit(self):
  with tempfile.TemporaryDirectory(dir='tmp') as d:
   path=Path(d)/'p.sqlite';c=VinaPoolCampaign(path,clock=lambda:0)
   spec={'model_version':'engine','receptor':'r','ligand':'l','conformer_bank':'input','region':'box','search_parameters':{'method':'native-mc','max_evals':0,'minima':9}}
   c.register_pool('p',spec,list(range(32)))
   for i in range(32):
    c=VinaPoolCampaign(path,clock=lambda:0);owner=str(i);lease=c.lease('p',owner);ch=c.commit(lease['lease'],owner,lease['binding'],'a'*64,samples=1);task=lease['tasks'][0]['task']
    if i==0:
     with self.assertRaises(ValueError):c.finish(lease['lease'],owner,lease['binding'],ch['id'],'a'*64,True,{})
     with self.assertRaises(LookupError):c.ordered_outputs('p')
     with self.assertRaises(ValueError):c.finish_outputs(lease['lease'],owner,lease['binding'],ch['id'],'a'*64,{},[])
     self.assertEqual(c.coverage('p')['completed'],0)
    c.finish_outputs(lease['lease'],owner,lease['binding'],ch['id'],'a'*64,{task:b'fixture'},[task])
    with self.assertRaises(ValueError):c.finish_outputs(lease['lease'],owner,lease['binding'],ch['id'],'a'*64,{task:b'fixture'},[task])
   self.assertTrue(c.coverage('p')['all_replay_verified'])
   self.assertEqual([r['ordinal'] for r in c.ordered_outputs('p',require_verified=True)],list(range(32)))
   with self.assertRaises(LookupError):c.lease('p','again')
   c.register_pool('alias',dict(spec,ligand='display-alias'),list(range(32)))
   self.assertTrue(c.coverage('alias')['aggregate_ready_provisional'])
   with self.assertRaises(LookupError):c.lease('alias','again')
   with self.assertRaises(ValueError):c.register_pool('budget-alias',dict(spec,search_parameters={**spec['search_parameters'],'max_evals':16000}),list(range(32)))
 def test_multi_run_bundle_preserves_provisional_distinction(self):
  with tempfile.TemporaryDirectory(dir='tmp') as d:
   c=VinaPoolCampaign(Path(d)/'p.sqlite',clock=lambda:0);spec={'model_version':'e','receptor':'r','ligand':'l','conformer_bank':'i','region':'b','search_parameters':{'max_evals':0}}
   c.register_pool('p',spec,list(range(8)));l=c.lease('p','x',jobs=8);ch=c.commit(l['lease'],'x',l['binding'],'a'*64,samples=2)
   ids=[t['task'] for t in l['tasks']];verified=[ids[j] for j,i in ch['draws']];c.finish_outputs(l['lease'],'x',l['binding'],ch['id'],'a'*64,{k:b'fixture' for k in ids},verified)
   s=c.coverage('p');self.assertTrue(s['aggregate_ready_provisional']);self.assertFalse(s['all_replay_verified']);self.assertEqual(s['replay_verified'],2)
   with self.assertRaises(ValueError):c.ordered_outputs('p',require_verified=True)
   with self.assertRaises(ValueError):c.mark_replay_verified(ids[0],'0'*64)
   for task in ids:c.mark_replay_verified(task,hashlib.sha256(b'fixture').hexdigest())
   self.assertTrue(c.coverage('p')['all_replay_verified'])
   self.assertEqual(len(c.ordered_outputs('p',require_verified=True)),8)
class ReseedTests(unittest.TestCase):
 """A re-issued unit must not accept a result computed for an earlier attempt."""
 spec={'model_version':'e','receptor':'r','ligand':'l','conformer_bank':'i','region':'b','search_parameters':{'max_evals':256000}}
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir='tmp');self.now=[0]
 def tearDown(self):self.tmp.cleanup()
 def campaign(self,seeds=(0,1,2,3)):
  c=VinaPoolCampaign(Path(self.tmp.name)/'p.sqlite',clock=lambda:self.now[0]);c.register_pool('p',self.spec,list(seeds));return c
 def seed(self,lease):return lease['tasks'][0]['spec']['search_parameters']['child_seed']
 def test_first_issue_keeps_registered_seed(self):
  c=self.campaign();self.assertEqual(self.seed(c.lease('p','x',ttl=10)),0)
 def test_expired_unit_is_reissued_with_new_recorded_seed(self):
  c=self.campaign();first=c.lease('p','x',ttl=10);self.now[0]=11;second=c.lease('p','y',ttl=10)
  self.assertEqual(first['tasks'][0]['task'],second['tasks'][0]['task'])
  self.assertNotEqual(self.seed(second),0);self.assertGreaterEqual(self.seed(second),rs.RESEED_FLOOR);self.assertLess(self.seed(second),rs.RESEED_CEIL)
  with c.transaction() as db:row=db.execute('SELECT old_seed,new_seed FROM pool_reseeds').fetchone()
  self.assertEqual((row['old_seed'],row['new_seed']),(0,self.seed(second)))
 def test_rejected_audit_reissues_with_new_seed(self):
  c=self.campaign();l=c.lease('p','x',ttl=60);ch=c.commit(l['lease'],'x',l['binding'],'a'*64,samples=1)
  c.finish(l['lease'],'x',l['binding'],ch['id'],'a'*64,False,{})
  again=c.lease('p','y',ttl=60);self.assertEqual(again['tasks'][0]['task'],l['tasks'][0]['task']);self.assertNotEqual(self.seed(again),self.seed(l))
 def test_each_reissue_draws_again(self):
  c=self.campaign();seeds=[]
  for i in range(3):l=c.lease('p','o%d'%i,ttl=10);seeds.append(self.seed(l));self.now[0]+=11
  self.assertEqual(len(set(seeds)),3)
 def test_reserved_seed_range_cannot_be_registered(self):
  c=VinaPoolCampaign(Path(self.tmp.name)/'q.sqlite',clock=lambda:0)
  with self.assertRaises(ValueError):c.register_pool('p',self.spec,[rs.RESEED_FLOOR])
 def test_colliding_draw_is_redrawn(self):
  c=self.campaign(seeds=(0,1));c.lease('p','x',ttl=10,jobs=2);self.now[0]=11
  with mock.patch.object(rs.secrets,'randbelow',side_effect=[5,5,7]):l=c.lease('p','y',ttl=10,jobs=2)
  self.assertEqual(sorted(t['spec']['search_parameters']['child_seed'] for t in l['tasks']),[rs.RESEED_FLOOR+5,rs.RESEED_FLOOR+7])
if __name__=='__main__':unittest.main()
