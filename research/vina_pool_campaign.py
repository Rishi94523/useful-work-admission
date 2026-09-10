"""Accumulate whole search units across sessions; atomic durable output + credit.

Trusted registration/verifier API, not an Internet endpoint or risk classifier.
The existing campaign transaction, commitment and challenge machinery is reused.
"""
import hashlib,json,secrets
from research.docking_campaign import Campaign,canonical

class VinaPoolCampaign(Campaign):
 def __init__(self,path,clock=None):
  if clock is None:super().__init__(path)
  else:super().__init__(path,clock)
  with self.transaction() as db:
   db.executescript('''CREATE TABLE IF NOT EXISTS pool_members(pool TEXT,task TEXT,ordinal INTEGER,PRIMARY KEY(pool,ordinal));
    CREATE TABLE IF NOT EXISTS pool_outputs(task TEXT PRIMARY KEY,payload BLOB NOT NULL,digest TEXT NOT NULL,verified INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS pool_attempts(task TEXT PRIMARY KEY,n INTEGER NOT NULL DEFAULT 0);''')
 def register_pool(self,pool,spec,seeds,cost=1):
  if not seeds or len(seeds)>1024 or len(set(seeds))!=len(seeds) or any(type(s)!=int or s<0 for s in seeds):raise ValueError('Invalid or duplicate child seeds')
  with self.transaction() as db:
   if db.execute('SELECT 1 FROM pool_members WHERE pool=?',(pool,)).fetchone():raise ValueError('Pool already registered')
   for i,seed in enumerate(seeds):
    params={**spec['search_parameters'],'child_seed':seed};unit={**spec,'search_parameters':params};identity={**unit,'ligand':'canonical-input'}
    # Do not manufacture credits by relabeling the campaign or changing a cap
    # on a previously registered seed. Pool order is aggregation metadata only.
    identity['search_parameters']={k:v for k,v in params.items() if k!='max_evals'}
    family=hashlib.sha256(canonical(identity)).hexdigest();task=family
    prior=db.execute('SELECT specification FROM units WHERE task=?',(task,)).fetchone()
    if prior:
     old=json.loads(prior['specification'])
     if old['search_parameters']!=params:raise ValueError('Previously registered seed at another budget')
    else:
     db.execute('INSERT INTO units VALUES(?,?,?,?,?,?,?,?,?,?,?)',(task,family,pool,spec['ligand'],0,1,cost,canonical(unit).decode(),'UNASSIGNED',None,None))
     db.execute('INSERT INTO pool_attempts VALUES(?,0)',(task,))
    db.execute('INSERT INTO pool_members VALUES(?,?,?)',(pool,task,i))
 def lease(self,pool,owner,jobs=1,ttl=600):
  if not owner or type(jobs)!=int or not 1<=jobs<=128 or not 0<ttl<=600:raise ValueError('Invalid lease')
  now=self.clock();lease=secrets.token_hex(16)
  with self.transaction() as db:
   self._expire(db,now)
   chosen=db.execute("SELECT u.*,p.ordinal FROM pool_members p JOIN units u ON p.task=u.task JOIN pool_attempts a ON a.task=u.task WHERE p.pool=? AND u.state IN ('UNASSIGNED','EXPIRED') AND a.n<3 ORDER BY p.ordinal LIMIT ?",(pool,jobs)).fetchall()
   if len(chosen)!=jobs:raise LookupError('Insufficient uncompleted units')
   tasks=[{'task':r['task'],'spec':json.loads(r['specification']),'start':0,'count':1,'estimated_cost':r['cost'],'ordinal':r['ordinal']} for r in chosen]
   payload={'lease':lease,'campaign':pool,'expires':now+ttl,'tasks':tasks};binding=hashlib.sha256(canonical(payload)).hexdigest();payload['binding']=binding
   db.execute('INSERT INTO leases(id,owner,issued,expires,status,tasks,binding) VALUES(?,?,?,?,?,?,?)',(lease,owner,now,now+ttl,'OPEN',canonical(tasks).decode(),binding))
   for r in chosen:db.execute("UPDATE units SET state='LEASED',lease=? WHERE task=?",(lease,r['task']))
  return payload
 def _before_challenge(self,db,tasks):
  for t in tasks:
    if db.execute('UPDATE pool_attempts SET n=n+1 WHERE task=? AND n<3',(t['task'],)).rowcount!=1:raise ValueError('Attempt cap')
 def finish(self,lease,owner,binding,challenge_id,commitment,accepted,result):
  if accepted:raise ValueError('Accepted pools require durable finish_outputs')
  return super().finish(lease,owner,binding,challenge_id,commitment,False,result)
 def finish_outputs(self,lease,owner,binding,challenge_id,root,outputs,verified_tasks):
  # Called only after trusted verification of commitment/openings. Full raw
  # pools/traces are durably stored in the SAME transaction as credit state.
  with self.transaction() as db:
   row=self._live(db,lease,owner,binding,'COMMITTED');tasks=json.loads(row['tasks']);ids={t['task'] for t in tasks}
   if row['commitment']!=root or json.loads(row['challenge'])['id']!=challenge_id:raise ValueError('Commitment/challenge mismatch')
   if set(outputs)!=ids or not set(verified_tasks)<=ids:raise ValueError('Missing/substituted outputs')
   for task,data in outputs.items():
    if not isinstance(data,bytes) or not 0<len(data)<=16000000:raise ValueError('Invalid bounded payload')
    db.execute('INSERT INTO pool_outputs VALUES(?,?,?,?)',(task,data,hashlib.sha256(data).hexdigest(),int(task in verified_tasks)))
   db.execute("UPDATE leases SET status='ACCEPTED',result=? WHERE id=?",(canonical({'provisional':True,'outputs':len(outputs)}).decode(),lease))
   db.execute("UPDATE units SET state='COMPLETED',completed_lease=?,lease=NULL WHERE lease=? AND state='LEASED'",(lease,lease))
 def coverage(self,pool):
  with self.transaction() as db:
   rows=db.execute('SELECT p.ordinal,u.state,o.verified FROM pool_members p JOIN units u ON u.task=p.task LEFT JOIN pool_outputs o ON o.task=u.task WHERE p.pool=? ORDER BY p.ordinal',(pool,)).fetchall()
   complete=sum(r['state']=='COMPLETED' for r in rows);verified=sum(r['verified']==1 for r in rows)
   return {'assigned_goal':len(rows),'completed':complete,'replay_verified':verified,'aggregate_ready_provisional':bool(rows) and complete==len(rows),'all_replay_verified':bool(rows) and verified==len(rows)}
