import hashlib,tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from research.pool_admission import PoolAdmission

class AdmissionTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir='tmp');self.now=[0]
 def tearDown(self):self.tmp.cleanup()
 def create(self,**kwargs):
  # Trusted-tier mechanics tests grant trust directly; the threshold has its own tests.
  kwargs.setdefault('trust_bundles',0)
  c=PoolAdmission(Path(self.tmp.name)/'policy.sqlite',clock=lambda:self.now[0],**kwargs);self.c=c
  c.register_pool('p',dict(model_version='fixture',receptor='r',ligand='l',conformer_bank='i',region='b',search_parameters={'max_evals':256000}),list(range(64)))
  return c
 def commit(self,c,owner='a'):
  l=c.request('p',owner);outputs={t['task']:b'fixture output' for t in l['tasks']};ch=c.commit(l['lease'],owner,l['binding'],c.output_root(l['binding'],outputs));return l,outputs,ch
 def submit(self,c,l,o,ch,owner='a'):return c.submit(l['lease'],owner,l['binding'],ch['id'],o)
 def verdict(self,l,o,ch,ok=True):return {t:(hashlib.sha256(o[t]).hexdigest(),ok) for t in self.c.audit_targets(l['lease'])}
 def test_fresh_identity_is_bundle_despite_zero_risk(self):
  c=self.create();l,o,ch=self.commit(c);self.assertEqual(len(o),4);self.assertEqual(set(ch),{'id'});self.assertEqual(self.submit(c,l,o,ch)['status'],'pending')
  with self.assertRaises(ValueError):c.redeem(l['lease'],'a')
  c.replay(l['lease'],self.verdict(l,o,ch));c.redeem(l['lease'],'a')
  with self.assertRaises(ValueError):c.redeem(l['lease'],'a')
 def test_trusted_quota_is_durable_and_not_renewed_by_unaudited_success(self):
  c=self.create(audit_probability=0);c.grant_trust('a',allowance=1);l,o,ch=self.commit(c);self.assertEqual(len(o),1);self.assertEqual(c.audit_targets(l['lease']),[]);self.assertEqual(self.submit(c,l,o,ch)['status'],'granted')
  reopened=PoolAdmission(c.path,clock=lambda:self.now[0],audit_probability=0);self.assertEqual(len(reopened.request('p','a')['tasks']),4)
 def test_selected_low_risk_waits_and_no_commit_reroll(self):
  c=self.create(audit_probability=1);c.grant_trust('a');l,o,ch=self.commit(c)
  with self.assertRaises(ValueError):c.commit(l['lease'],'a',l['binding'],c.output_root(l['binding'],o))
  self.assertEqual(self.submit(c,l,o,ch)['status'],'pending');self.assertEqual(c.request('p','a')['status'],'pending')
  with self.assertRaises(ValueError):c.redeem(l['lease'],'a')
  c.replay(l['lease'],self.verdict(l,o,ch));c.redeem(l['lease'],'a')
 def test_late_failure_preserves_consumed_access_but_quarantines_science(self):
  c=self.create(policy='deferred',audit_probability=1);c.grant_trust('a');l,o,ch=self.commit(c);self.submit(c,l,o,ch);c.redeem(l['lease'],'a')
  self.assertEqual(c.request('p','a')['status'],'pending');r=c.replay(l['lease'],self.verdict(l,o,ch,False));self.assertTrue(r['prior_access_irreversible'])
  with self.assertRaises(ValueError):c.ordered_outputs('p',False)
  with self.assertRaises(ValueError):c.grant_trust('a')
  self.assertEqual(c.request('p','a')['tier'],'bundle')
 def test_capacity_reservation_prevents_audit_downgrade(self):
  c=self.create(audit_probability=1,capacity=1);c.grant_trust('a');l,o,ch=self.commit(c);self.submit(c,l,o,ch)
  self.assertEqual(c.request('p','b')['status'],'capacity');self.now[0]=121;self.assertEqual(c.request('p','b')['status'],'assigned')
  with self.assertRaises(ValueError):c.replay(l['lease'],self.verdict(l,o,ch))
 def test_output_and_verdict_substitution_rejected(self):
  c=self.create();l,o,ch=self.commit(c);bad=dict(o);bad[next(iter(bad))]=b'substitution'
  with self.assertRaises(ValueError):self.submit(c,l,bad,ch)
  self.submit(c,l,o,ch)
  with self.assertRaises(ValueError):c.replay(l['lease'],{})
  with self.assertRaises(ValueError):c.replay(l['lease'],{t:('0'*64,True) for t in self.verdict(l,o,ch)})
 def test_concurrent_requests_share_one_owner_and_global_capacity(self):
  c=self.create(capacity=3)
  with ThreadPoolExecutor(max_workers=8) as p:results=list(p.map(lambda _:c.request('p','same'),range(8)))
  self.assertEqual(sum(r['status']=='assigned' for r in results),1)
  with ThreadPoolExecutor(max_workers=8) as p:results=list(p.map(lambda i:c.request('p','owner'+str(i)),range(8)))
  self.assertEqual(sum(r['status']=='assigned' for r in results),2)

 def test_commit_discloses_no_audit_information(self):
  for kw in ({},{'audit_probability':1},{'policy':'deferred','audit_probability':1}):
   self.tmp.cleanup();self.tmp=tempfile.TemporaryDirectory(dir='tmp');c=self.create(**kw)
   if kw:c.grant_trust('a')
   l,o,ch=self.commit(c);self.assertEqual(set(ch),{'id'})
 def test_selected_trusted_client_is_audited_after_upload_even_if_it_leaves(self):
  c=self.create(audit_probability=1);c.grant_trust('a');l,o,ch=self.commit(c)
  self.assertEqual(self.submit(c,l,o,ch)['status'],'pending')
  r=c.replay(l['lease'],self.verdict(l,o,ch,False));self.assertEqual(r['status'],'rejected')
  with self.assertRaises(ValueError):c.grant_trust('a')

 def earn_bundle(self,c,owner):
  l,o,ch=self.commit(c,owner);self.assertEqual(self.submit(c,l,o,ch,owner)['status'],'pending');c.replay(l['lease'],self.verdict(l,o,ch));self.now[0]+=121
 def test_trust_requires_three_audited_bundles_by_default(self):
  c=self.create(trust_bundles=3)
  for n in range(3):
   with self.assertRaises(ValueError):c.grant_trust('a')
   self.earn_bundle(c,'a')
  c.grant_trust('a');self.assertEqual(c.request('p','a')['tier'],'trusted')
 def test_rejected_bundles_do_not_count_and_quarantine_still_refuses(self):
  c=self.create(trust_bundles=1);l,o,ch=self.commit(c);self.submit(c,l,o,ch);c.replay(l['lease'],self.verdict(l,o,ch,False))
  with self.assertRaises(ValueError):c.grant_trust('a')
 def test_default_threshold_is_three(self):
  self.assertEqual(PoolAdmission(Path(self.tmp.name)/'d.sqlite',clock=lambda:0).trust_bundles,3)

 def test_rejected_requests_preserve_fractional_global_refill(self):
  c=self.create()
  with c.transaction() as db:db.execute('UPDATE admission_budget SET tokens=0,updated=0')
  outcomes=[]
  for i in range(1,9):
   self.now[0]=i/8
   outcomes.append(c.request('p','fresh-'+str(i))['status'])
  self.assertEqual(outcomes.count('assigned'),2)
  with c.transaction() as db:
   self.assertEqual(db.execute('SELECT tokens FROM admission_budget').fetchone()[0],0)

if __name__=='__main__':unittest.main()
