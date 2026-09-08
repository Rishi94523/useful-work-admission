import tempfile,unittest
from pathlib import Path
from research.whole_run_campaign import WholeRunCampaign

class WholeRuns(unittest.TestCase):
 def test_consumed_work_credit_and_seed_alias(self):
  with tempfile.TemporaryDirectory(dir='tmp') as d:
   c=WholeRunCampaign(Path(d)/'c.sqlite');args=('engine','maps','ligand','input','box')
   c.register('science',*args,0,16,4000,64)
   # A precomputed result may later earn a one-use credit; no fresh-CPU flag.
   lease=c.lease('science','worker');units=c.units(lease)
   self.assertEqual(len(units),16);self.assertEqual(units[1]['seed'],117736)
   challenge=c.commit(lease['lease'],'worker',lease['binding'],'a'*64,4)
   self.assertEqual(len(set(c.flat_draws(lease,challenge))),4)
   c.finish(lease['lease'],'worker',lease['binding'],challenge['id'],'a'*64,True,{'scientific_status':'provisional','credit_kind':'one-use-coverage'})
   with self.assertRaises(LookupError):c.lease('science','colluder')
   with self.assertRaises(ValueError):c.register('renamed',*args,0,16,16000,256)
   with self.assertRaises(ValueError):c.finish(lease['lease'],'worker',lease['binding'],challenge['id'],'a'*64,True,{})
   c.register('science',*args,16,16,16000,256)
   self.assertEqual(c.lease('science','worker')['tasks'][0]['start'],16)

 def test_abandoned_work_is_reassignable(self):
  with tempfile.TemporaryDirectory(dir='tmp') as d:
   now=[0];c=WholeRunCampaign(Path(d)/'c.sqlite',clock=lambda:now[0]);c.register('science','engine','maps','ligand','input','box',0,16,4000,64)
   first=c.lease('science','a',ttl=1);now[0]=2;second=c.lease('science','b')
   self.assertEqual(c.units(first),c.units(second));self.assertNotEqual(first['binding'],second['binding'])
   with self.assertRaises(ValueError):c.commit(first['lease'],'a',first['binding'],'a'*64)
if __name__=='__main__':unittest.main()
