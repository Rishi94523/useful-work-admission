import hashlib,tempfile,unittest
from pathlib import Path
from research.vina_pool_campaign import VinaPoolCampaign
class PoolTests(unittest.TestCase):
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
if __name__=='__main__':unittest.main()
