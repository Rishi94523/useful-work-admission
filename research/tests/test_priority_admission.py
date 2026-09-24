import hashlib,secrets,tempfile,unittest
from pathlib import Path
from research.priority_admission import PriorityAdmission,solve_effort
from research.ticket_admission import encoded

SPEC={'campaign':'fixture','input_hashes':['fixture-only'],'max_evals':256000}

class PriorityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='tmp');self.now=[0.0]
  self.c=PriorityAdmission(Path(self.tmp.name)/'q.sqlite',secrets.token_bytes(32),SPEC,clock=lambda:self.now[0],sub_bits=4,issuance_rate=1000)
  self.n=0
 def tearDown(self):self.tmp.cleanup()
 def prepare(self,trusted=False):
  self.n+=1;owner=('trusted-' if trusted else 'new-')+str(self.n);t=self.c.issue(owner,trusted=trusted)
  body=encoded({str(s):'honest' for s in t['assignment']['seeds']});root=hashlib.sha256(body).hexdigest()
  return owner,t,body,root
 def send(self,effort=0,trusted=False):
  owner,t,body,root=self.prepare(trusted);o=self.c.offer(t['ticket'],root,owner)
  proof=solve_effort(o['challenge'],o['sub_bits'],effort) if o['status']=='effort' and effort else None
  return o,self.c.submit(t['ticket'],root,body,owner,proof)
 def fill(self,effort=0):
  return [self.send(effort)[1] for _ in range(8)]
 def test_no_pressure_costs_nothing(self):
  o,r=self.send();self.assertEqual(o['status'],'ready');self.assertEqual(r['status'],'queued');self.assertEqual(r['effort'],0)
 def test_higher_bid_evicts_lowest_and_equal_bid_does_not(self):
  first=self.fill()
  o,equal=self.send(0);self.assertEqual(o['status'],'effort');self.assertEqual(equal['status'],'queue_full')
  o,higher=self.send(3);self.assertEqual(higher['status'],'queued');self.assertTrue(higher['evicted_other'])
  self.assertEqual(sum(self.c.state(r['id'])=='EVICTED' for r in first),1)
 def test_replay_order_is_highest_effort_first(self):
  self.fill();_,top=self.send(5);_,mid=self.send(2)
  self.assertEqual(self.c.claim('new')['id'],top['id']);self.assertEqual(self.c.claim('new')['id'],mid['id'])
 def test_claimed_submission_cannot_be_evicted(self):
  first=self.fill();claimed=self.c.claim('new')
  for _ in range(8):self.send(9)
  self.assertEqual(self.c.state(claimed['id']),'AUDITING')
  self.c.finish(claimed['id'],(claimed['root'],True),lambda db,row:None);self.assertEqual(self.c.state(claimed['id']),'GRANTED')
 def test_invalid_proofs_count_as_no_effort(self):
  self.fill();owner,t,body,root=self.prepare();o=self.c.offer(t['ticket'],root,owner);good=solve_effort(o['challenge'],o['sub_bits'],3)
  bad_nonce=dict(good,nonces=good['nonces'][:-1]+[good['nonces'][-1]+1])
  duplicate=dict(good,nonces=[good['nonces'][0]]*3)
  owner2,t2,body2,root2=self.prepare();foreign=solve_effort(self.c.offer(t2['ticket'],root2,owner2)['challenge'],4,3)
  for proof in (bad_nonce,duplicate,foreign,{'nonces':[1]},{'challenge':'x.y','nonces':[1]}):
   self.assertEqual(self.c.effort_of(self.c._ticket(t['ticket'],owner),root,proof),0)
  self.assertEqual(self.c.effort_of(self.c._ticket(t['ticket'],owner),root,good),3)
 def test_suggestion_rises_under_pressure_then_decays(self):
  self.fill(0);o,_=self.send(0);self.assertGreaterEqual(o['suggested'],1)
  for _ in range(8):self.c.claim('new')
  self.now[0]+=60;o,_=self.send(0);self.assertEqual(o.get('suggested',0),0)
 def test_established_users_never_bid_and_keep_their_seats(self):
  self.fill(0)
  for _ in range(8):self.send(9)
  o,r=self.send(trusted=True);self.assertEqual(o['status'],'ready');self.assertEqual(r['status'],'queued')

if __name__=='__main__':unittest.main()
