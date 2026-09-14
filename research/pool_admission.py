"""Trusted-service admission adapter; frozen scientific scheduler underneath.

Not an HTTP authentication boundary. Identity, trust grants and replay verdicts
must come from trusted services. No client-provided risk or success flags.
"""
from contextlib import contextmanager
import hashlib,json,secrets,threading
from research.adaptive_admission import AdaptiveAdmission
from research.docking_campaign import Campaign,canonical
from research.vina_pool_campaign import VinaPoolCampaign

class PoolAdmission(VinaPoolCampaign,AdaptiveAdmission):
 def __init__(self,path,clock=None,*,policy='immediate',audit_probability=.1,capacity=16,bundle=4,q=1):
  if policy not in ('immediate','deferred') or not 0<=audit_probability<=1 or not 1<=q<=bundle<=128 or capacity<1:raise ValueError('Policy')
  self.local=threading.local();self.policy=policy;self.probability=audit_probability;self.capacity=capacity;self.bundle=bundle;self.q=q
  super().__init__(path,clock)
  with self.transaction() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS pool_trust(owner TEXT PRIMARY KEY,remaining INTEGER,until REAL,revoked INTEGER);
   CREATE TABLE IF NOT EXISTS pool_policy(lease TEXT PRIMARY KEY,owner TEXT,policy TEXT,q INTEGER,selected INTEGER,state TEXT,payload TEXT);
   CREATE TABLE IF NOT EXISTS pool_credits(lease TEXT PRIMARY KEY,owner TEXT,state TEXT);
   CREATE TABLE IF NOT EXISTS pool_quarantine(owner TEXT PRIMARY KEY,reason TEXT);''')

 def _expire(self,db,now):
  AdaptiveAdmission._expire(self,db,now)
  db.execute("UPDATE pool_policy SET state='EXPIRED',payload=NULL WHERE state IN ('OPEN','COMMITTED','WAITING') AND lease IN (SELECT id FROM leases WHERE status='EXPIRED')")

 @contextmanager
 def transaction(self):
  # Reuse one write transaction across the existing risk/scheduler operations.
  active=getattr(self.local,'db',None)
  if active is not None:yield active;return
  with Campaign.transaction(self) as db:
   self.local.db=db
   try:yield db
   finally:self.local.db=None

 def grant_trust(self,owner,allowance=10,ttl=3600):
  if not owner or type(allowance)!=int or not 1<=allowance<=100 or not 0<ttl<=86400:raise ValueError('Trust grant')
  with self.transaction() as db:
   if db.execute('SELECT 1 FROM pool_quarantine WHERE owner=?',(owner,)).fetchone():raise ValueError('Quarantined identity')
   db.execute('INSERT OR REPLACE INTO pool_trust VALUES(?,?,?,0)',(owner,allowance,self.clock()+ttl))

 def lease(self,*a,**k):raise ValueError('Use request')
 def lease_many(self,*a,**k):raise ValueError('Use request')
 def finish_outputs(self,*a,**k):raise ValueError('Use submit and trusted replay')
 def finish(self,*a,**k):raise ValueError('Use trusted replay')

 def request(self,pool,identity):
  if not isinstance(identity,str) or not 1<=len(identity)<=128:raise ValueError('Identity')
  with self.transaction() as db:
   now=self.clock();self._expire(db,now)
   # Existing global token bucket and reputation scoring are retained.
   b=db.execute('SELECT * FROM admission_budget WHERE id=1').fetchone();tokens=min(self.global_burst,b['tokens']+max(0,now-b['updated'])*self.global_rate)
   db.execute('UPDATE admission_budget SET tokens=?,updated=? WHERE id=1',(max(0,tokens-1),now))
   if tokens<1:return {'status':'capacity'}
   db.execute('DELETE FROM requests WHERE at<?',(now-10,));velocity=db.execute('SELECT count(*) FROM requests WHERE identity=?',(identity,)).fetchone()[0]+1
   db.execute('INSERT INTO requests VALUES(?,?)',(identity,now));s=self._state(db,identity,now);s=self._event(db,identity,now,'request',(6 if velocity>3 else 0)+min(8,2*s['streak']))
   if s['cooldown']>now or s['score']>=60:return {'status':'cooldown'}
   outstanding="SELECT p.* FROM pool_policy p JOIN leases l ON l.id=p.lease WHERE l.status IN ('OPEN','COMMITTED') OR p.state='DEFERRED'"
   rows=db.execute(outstanding).fetchall()
   if any(r['owner']==identity for r in rows):return {'status':'pending'}
   if len(rows)>=self.capacity:return {'status':'capacity'}
   trust=db.execute('SELECT * FROM pool_trust WHERE owner=?',(identity,)).fetchone()
   low=bool(trust and not trust['revoked'] and trust['remaining']>0 and trust['until']>now and s['score']<15)
   n=1 if low else self.bundle;lease=VinaPoolCampaign._lease_plan(self,{pool:n},identity,120)
   if low:db.execute('UPDATE pool_trust SET remaining=remaining-1 WHERE owner=?',(identity,))
   db.execute('INSERT INTO pool_policy VALUES(?,?,?,?,NULL,?,NULL)',(lease['lease'],identity,self.policy if low else 'bundle',1 if low else self.q,'OPEN'))
   return dict(status='assigned',tier='trusted' if low else 'bundle',**lease)

 @staticmethod
 def output_root(binding,outputs):
  if not outputs or any(not isinstance(v,bytes) or not 0<len(v)<=16000000 for v in outputs.values()):raise ValueError('Outputs')
  return hashlib.sha256(canonical({'binding':binding,'digests':{k:hashlib.sha256(v).hexdigest() for k,v in outputs.items()}})).hexdigest()

 def commit(self,lease,owner,binding,commitment):
  with self.transaction() as db:
   p=db.execute('SELECT * FROM pool_policy WHERE lease=? AND owner=?',(lease,owner)).fetchone()
   if not p:raise ValueError('Policy')
   challenge=Campaign.commit(self,lease,owner,binding,commitment,samples=p['q'])
   selected=p['policy']=='bundle' or secrets.randbelow(1000000)<self.probability*1000000
   db.execute("UPDATE pool_policy SET selected=?,state='COMMITTED' WHERE lease=?",(int(selected),lease))
   return {**challenge,'replay_required':selected,'deferred':selected and p['policy']=='deferred'}

 def submit(self,lease,owner,binding,challenge_id,outputs):
  with self.transaction() as db:
   row=self._live(db,lease,owner,binding,'COMMITTED');p=db.execute('SELECT * FROM pool_policy WHERE lease=?',(lease,)).fetchone()
   if p['state']!='COMMITTED':raise ValueError('Already submitted')
   ids={x['task'] for x in json.loads(row['tasks'])}
   if set(outputs)!=ids or self.output_root(binding,outputs)!=row['commitment'] or json.loads(row['challenge'])['id']!=challenge_id:raise ValueError('Commitment/output substitution')
   db.execute('UPDATE pool_policy SET payload=? WHERE lease=?',(json.dumps({k:v.hex() for k,v in outputs.items()}),lease))
   if p['selected'] and p['policy']!='deferred':
    db.execute("UPDATE pool_policy SET state='WAITING' WHERE lease=?",(lease,));return {'status':'pending'}
   VinaPoolCampaign.finish_outputs(self,lease,owner,binding,challenge_id,row['commitment'],outputs,[])
   db.execute('UPDATE pool_policy SET state=?,payload=NULL WHERE lease=?',('DEFERRED' if p['selected'] else 'DONE',lease))
   db.execute("INSERT INTO pool_credits VALUES(?,?,'GRANTED')",(lease,owner));return {'status':'granted'}

 def replay(self,lease,verdicts):
  """Trusted complete-unit replay only; bind verdict to durable output digest."""
  with self.transaction() as db:
   self._expire(db,self.clock());p=db.execute('SELECT * FROM pool_policy WHERE lease=?',(lease,)).fetchone();l=db.execute('SELECT * FROM leases WHERE id=?',(lease,)).fetchone()
   if not p or p['state'] not in ('WAITING','DEFERRED') or l['status'] not in ('COMMITTED','ACCEPTED'):raise ValueError('No live audit')
   tasks=json.loads(l['tasks']);challenge=json.loads(l['challenge']);selected={tasks[j]['task'] for j,_ in challenge['draws']}
   outputs=({k:bytes.fromhex(v) for k,v in json.loads(p['payload']).items()} if p['payload'] else {t['task']:bytes(db.execute('SELECT payload FROM pool_outputs WHERE task=?',(t['task'],)).fetchone()['payload']) for t in tasks})
   if self.output_root(l['binding'],outputs)!=l['commitment']:raise ValueError('Stored commitment mismatch')
   if set(verdicts)!=selected:raise ValueError('Incomplete audit')
   for task,(digest,ok) in verdicts.items():
    if type(ok)!=bool or digest!=hashlib.sha256(outputs[task]).hexdigest():raise ValueError('Unbound verdict')
   good=all(ok for _,ok in verdicts.values());owner=p['owner']
   if not good:
    db.execute('UPDATE pool_trust SET revoked=1 WHERE owner=?',(owner,));db.execute("INSERT OR REPLACE INTO pool_quarantine VALUES(?,'replay mismatch')",(owner,));db.execute("UPDATE pool_credits SET state='REVOKED' WHERE owner=? AND state='GRANTED'",(owner,));self._event(db,owner,self.clock(),'audit_failure',18,failure=True)
    if p['state']=='WAITING':Campaign.finish(self,lease,owner,l['binding'],challenge['id'],l['commitment'],False,{})
    db.execute("UPDATE pool_policy SET state='FAILED',payload=NULL WHERE lease=?",(lease,));return {'status':'rejected','prior_access_irreversible':p['state']=='DEFERRED'}
   if p['state']=='WAITING':
    VinaPoolCampaign.finish_outputs(self,lease,owner,l['binding'],challenge['id'],l['commitment'],outputs,selected);db.execute("INSERT INTO pool_credits VALUES(?,?,'GRANTED')",(lease,owner))
   else:
    for task in selected:VinaPoolCampaign.mark_replay_verified(self,task,hashlib.sha256(outputs[task]).hexdigest())
   db.execute("UPDATE pool_policy SET state='DONE',payload=NULL WHERE lease=?",(lease,));self._event(db,owner,self.clock(),'success',-2,success=True);return {'status':'granted'}

 def redeem(self,lease,owner):
  with self.transaction() as db:
   if db.execute("UPDATE pool_credits SET state='REDEEMED' WHERE lease=? AND owner=? AND state='GRANTED'",(lease,owner)).rowcount!=1:raise ValueError('No one-use credit')

 def ordered_outputs(self,pool,require_verified=True):
  with self.transaction() as db:
   if db.execute('SELECT 1 FROM pool_members p JOIN units u ON u.task=p.task JOIN leases l ON l.id=u.completed_lease JOIN pool_quarantine q ON q.owner=l.owner WHERE p.pool=?',(pool,)).fetchone():raise ValueError('Scientific aggregate quarantined')
   return VinaPoolCampaign.ordered_outputs(self,pool,require_verified)
