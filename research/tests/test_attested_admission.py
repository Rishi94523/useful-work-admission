import hashlib,secrets,tempfile,unittest
from pathlib import Path
from research.attested_admission import AttestedAdmission,MockAttester
from research.priority_admission import solve_effort
from research.ticket_admission import encoded

SPEC={'campaign':'fixture','input_hashes':['fixture-only'],'max_evals':256000}

class AttestedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='tmp');self.now=[0.0];clock=lambda:self.now[0]
  self.issuer=MockAttester('https://origin.example',per_device=2,window_s=3600,clock=clock)
  self.c=AttestedAdmission(Path(self.tmp.name)/'q.sqlite',secrets.token_bytes(32),SPEC,clock=clock,sub_bits=4,
                           issuance_rate=1000,verify_attestation=self.issuer.verify)
  self.n=0
 def tearDown(self):self.tmp.cleanup()
 def send(self,token=None,effort=0):
  self.n+=1;owner='u-%d'%self.n;t=self.c.issue(owner,attestation=token)
  if t['status']!='ticket':return t,None,None
  body=encoded({str(s):'honest' for s in t['assignment']['seeds']});root=hashlib.sha256(body).hexdigest()
  o=self.c.offer(t['ticket'],root,owner)
  proof=solve_effort(o['challenge'],o['sub_bits'],effort) if o['status']=='effort' and effort else None
  return t,o,self.c.submit(t['ticket'],root,body,owner,proof)
 def token(self):
  self.n+=1;return self.issuer.token('device-%d'%self.n)
 def test_valid_token_gives_attested_lane_without_puzzle(self):
  for _ in range(8):self.send(effort=9)
  t,o,r=self.send(self.token());self.assertEqual(t['assignment']['tier'],'attested')
  self.assertEqual(o['status'],'ready');self.assertEqual(r['status'],'queued')
 def test_forged_foreign_and_reused_tokens_are_refused(self):
  good=self.token();self.assertEqual(self.send(good)[0]['assignment']['tier'],'attested')
  self.assertEqual(self.send(good)[0]['status'],'attestation_spent')
  other=MockAttester('https://other.example',per_device=2,window_s=3600,clock=lambda:0).token('d')
  foreign=MockAttester('https://origin.example',per_device=2,window_s=3600,clock=lambda:0).token('d')
  body,tag=self.token().rsplit('.',1)
  for bad in (other,foreign,body+'.'+'0'*64,'nonsense',123):
   self.assertEqual(self.send(bad)[0]['status'],'attestation_invalid')
 def test_issuer_caps_tokens_per_device(self):
  self.assertIsNotNone(self.issuer.token('d'));self.assertIsNotNone(self.issuer.token('d'))
  self.assertIsNone(self.issuer.token('d'));self.now[0]+=3600;self.assertIsNotNone(self.issuer.token('d'))
 def test_attested_submissions_are_replayed_first_and_never_evicted(self):
  anon=[self.send(effort=5)[2] for _ in range(3)];_,_,att=self.send(self.token())
  self.assertEqual(self.c.next_newcomer()['id'],att['id']);self.assertIn(self.c.next_newcomer()['id'],{r['id'] for r in anon})
  _,_,att2=self.send(self.token())
  for _ in range(8):self.send(effort=9)
  self.assertEqual(self.c.state(att2['id']),'QUEUED')
 def test_attested_lane_has_its_own_seats(self):
  att=[self.send(self.token())[2]['status'] for _ in range(8)];self.assertEqual(att,['queued']*8)
  self.assertEqual(self.send(self.token())[2]['status'],'queue_full')
  # A full attested lane neither prices nor blocks anonymous newcomers.
  t,o,r=self.send();self.assertEqual(o['status'],'ready');self.assertEqual(r['status'],'queued')
 def test_rate_limited_issue_does_not_spend_the_token(self):
  self.c.issuance_rate=1e-9
  for _ in range(32):self.c.issue('flood',attestation=None)
  tok=self.token()
  for _ in range(32):self.c.issue('x',attestation=self.issuer.token('farm-%d'%_))
  self.assertEqual(self.c.issue('late',attestation=tok)['status'],'rate_limited')
  self.c.issuance_rate=1000;self.now[0]+=1;self.assertEqual(self.c.issue('late',attestation=tok)['status'],'ticket')

if __name__=='__main__':unittest.main()
