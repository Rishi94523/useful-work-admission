"""Phase 2 of the adversarial evaluation: admission economics on the real scheduler.

Attackers drive the unmodified PoolAdmission scheduler under a simulated clock.
Every audit verdict is drawn from the phase-1 replay measurements for that kind
of payload rather than assumed: honest payloads from the honest replay records,
fabricated payloads from the substitution records, reduced-budget payloads from
the partial-work records.

The headline metric is the attacker discount factor: honest-unit work the
attacker spends per successful admission, divided by what an honest client
spends per admission in the same tier. A hashcash puzzle has a factor of 1.0 by
construction, since no strategy solves it for less than its cost. A factor below
1.0 means cheating is cheaper than honest work in that configuration.

Rows marked deployed use the scheduler exactly as committed. Other attempt caps
and seed invalidation are counterfactuals, run through a test-only subclass that
changes only that behaviour. Strategies are specific rather than optimal, so a
reported factor is an upper bound on what a capable attacker pays.

See docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md, amendment 2.
"""
import hashlib,json,os,random,shutil,sys,tempfile
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.pool_admission import PoolAdmission

PHASE1=ROOT/'local-research/adversarial-2026-09-23/phase1.jsonl'
OUT=ROOT/'local-research/adversarial-2026-09-23'
PROTOCOL=ROOT/'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'
TARGET=300
POOL_SIZE=1024
TTL=120
UNIT_S=1.52
DEPLOYED_CAP=3
SEED=20260923
GIVE_UP=2000
WORKERS=12

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class Verdicts:
 """Audit outcomes resampled from real phase-1 replay records."""
 def __init__(self,rng):
  rows=[json.loads(s) for s in PHASE1.read_text().splitlines() if s.strip()];self.rng=rng
  self.table={'honest':[r['accepted'] for r in rows if r.get('attack')=='honest'],
              'fabricated':[r['accepted'] for r in rows if r.get('attack')=='A1_substitution']}
  for b in (64000,128000):
   for mode in ('pool_only','pool_and_trace'):
    self.table[('partial',b,mode)]=[r['accepted_'+mode] for r in rows if r.get('attack')=='A2_partial' and r['budget']==b]
  assert all(self.table.values()),'Phase-1 records missing'
 def __call__(self,kind):return bool(self.rng.choice(self.table[kind]))

def scheduler(cap):
 """The deployed scheduler at the deployed cap; a counterfactual cap otherwise."""
 if cap==DEPLOYED_CAP:return PoolAdmission
 class Capped(PoolAdmission):
  # request() calls VinaPoolCampaign._lease_plan by class, so leasing cannot be
  # overridden. Instead keep the true count in a side table and drive the
  # deployed column the unchanged lease filter reads (leasable while n<3).
  def _before_challenge(self,db,tasks):
   db.execute('CREATE TABLE IF NOT EXISTS counterfactual_attempts(task TEXT PRIMARY KEY,n INTEGER NOT NULL)')
   for t in tasks:
    db.execute('INSERT OR IGNORE INTO counterfactual_attempts VALUES(?,0)',(t['task'],))
    n=db.execute('SELECT n FROM counterfactual_attempts WHERE task=?',(t['task'],)).fetchone()[0]
    if n>=cap:raise ValueError('Attempt cap')
    db.execute('UPDATE counterfactual_attempts SET n=? WHERE task=?',(n+1,t['task']))
    db.execute('UPDATE pool_attempts SET n=? WHERE task=?',(3 if n+1>=cap else 0,t['task']))
 return Capped

class World:
 def __init__(self,work,verdicts,cap=DEPLOYED_CAP,**kw):
  self.now=[0.0];self.dir=Path(tempfile.mkdtemp(dir=work));self.cap=cap
  self.c=scheduler(cap)(self.dir/'s.sqlite',clock=lambda:self.now[0],**kw)
  self.pools=0;self.verdicts=verdicts;self.replayed=0;self.ids=0;self._new_pool()
 def _new_pool(self):
  base=self.pools*POOL_SIZE;self.pools+=1;self.pool='p%d'%self.pools
  spec=dict(model_version='economics',receptor='r',ligand='l',conformer_bank='i',region='b',search_parameters={'max_evals':256000})
  self.c.register_pool(self.pool,spec,list(range(base,base+POOL_SIZE)))
 def identity(self):self.ids+=1;return 'id%d'%self.ids
 def request(self,who):
  try:return self.c.request(self.pool,who)
  except LookupError:self._new_pool();return self.c.request(self.pool,who)
 def advance(self,s):self.now[0]+=s
 def audit(self,lease,outputs,kinds,ch):
  drawn=[lease['tasks'][j]['task'] for j,_ in ch['draws']];self.replayed+=len(drawn)
  return self.c.replay(lease['lease'],{t:(hashlib.sha256(outputs[t]).hexdigest(),self.verdicts(kinds[t])) for t in drawn})
 def exhausted(self):
  with self.c.transaction() as db:
   # n>=3 marks an exhausted task in both the deployed and counterfactual paths.
   return db.execute("SELECT count(*) FROM pool_attempts a JOIN units u ON u.task=a.task WHERE a.n>=3 AND u.state!='COMPLETED'").fetchone()[0]
 def close(self):shutil.rmtree(self.dir,ignore_errors=True)

def attempt(w,who,lease,payload,submit_if_selected):
 """Commit, see the challenge, then submit or abandon.

 Returns (admitted, non-honest units retained after any audit). The scheduler
 reveals whether and what it will audit at commit, before any upload.
 """
 outputs={t:v[0] for t,v in payload.items()};kinds={t:v[1] for t,v in payload.items()}
 ch=w.c.commit(lease['lease'],who,lease['binding'],w.c.output_root(lease['binding'],outputs))
 drawn={lease['tasks'][j]['task'] for j,_ in ch['draws']}
 if ch['replay_required'] and not submit_if_selected(drawn,kinds,ch):
  w.advance(TTL+1);return False,0
 r=w.c.submit(lease['lease'],who,lease['binding'],ch['id'],outputs)
 if r['status']=='pending':r=w.audit(lease,outputs,kinds,ch)
 if r['status']!='granted':return False,0
 retained=sum(1 for k in kinds.values() if k!='honest')
 if ch.get('deferred') and w.audit(lease,outputs,kinds,ch)['status']=='rejected':retained=0
 return True,retained

def unit_keys(lease):
 """(task, seed) for each leased unit. A cached result is only valid for the
 same task at the same seed; a scheduler that reseeds on retry breaks reuse."""
 return [(x['task'],x['spec']['search_parameters']['child_seed']) for x in lease['tasks']]

def only_honest_drawn(drawn,kinds,ch):return all(kinds[t]=='honest' for t in drawn)

def bundle_attack(verdicts,work,*,q,k,cap=DEPLOYED_CAP,cache='reuse',partial=None,adaptive=True):
 """k honest units per bundle of four, the rest fabricated, or all reduced-budget.

 cache='reuse' is deployed behaviour: a result computed for a task stays valid
 if that task is leased again. cache='invalid' models reseeding a task after a
 failed or abandoned attempt, so earlier work is useless.
 """
 w=World(work,verdicts,cap=cap,q=q);done=set();spent=0.0;admitted=retained=attempts=0
 try:
  # Stop a configuration after 2,000 attempts without a single admission.
  while admitted<TARGET and attempts<TARGET*40 and not (admitted==0 and attempts>=GIVE_UP):
   who=w.identity();lease=w.request(who)
   if lease.get('status')!='assigned':w.advance(TTL+1);continue
   attempts+=1;payload={}
   for i,(t,seed) in enumerate(unit_keys(lease)):
    if partial:
     if (t,seed) not in done:spent+=partial[0]/256000;done.add((t,seed))
     payload[t]=(b'partial:'+t.encode(),('partial',)+partial)
    elif i<k:
     if (t,seed) not in done:spent+=1;done.add((t,seed))
     payload[t]=(b'honest:'+t.encode(),'honest')
    else:payload[t]=(b'fabricated:'+t.encode(),'fabricated')
   w.advance(UNIT_S*(k if not partial else 4*partial[0]/256000))
   rule=only_honest_drawn if (adaptive and not partial) else (lambda *a:True)
   ok,g=attempt(w,who,lease,payload,rule)
   if ok:admitted+=1;retained+=g
   if cache=='invalid':done.clear()
  per=lambda x:x/admitted if admitted else None
  return {'admissions':admitted,'attempts':attempts,'work_units':spent,'work_per_admission':per(spent),
          'discount':per(spent)/4 if admitted else None,'nonhonest_units_retained_per_admission':per(retained),
          'replayed_units_per_admission':per(w.replayed),'units_burned_by_cap':w.exhausted(),'units_burned_per_admission':per(w.exhausted())}
 finally:w.close()

def trusted_attack(verdicts,work,*,policy,p,G,acquire):
 """Earn trust with G admitted bundles, then submit fabricated trusted units.

 The trust grant after G admitted bundles is an assumed trusted-service policy;
 the scheduler itself leaves grant_trust to an external service.
 acquire='honest' earns each bundle with four honest units. acquire='cached'
 computes one unit per bundle and abandons whenever a fabricated unit is drawn,
 reusing that unit on re-lease, as in the deployed-cache bundle attack.
 """
 w=World(work,verdicts,policy=policy,audit_probability=p);spent=0.0;fraud=retained=identities=caught=0;done=set()
 submit_rule=(lambda *a:True) if policy=='deferred' else (lambda *a:False)
 try:
  while fraud<TARGET and identities<3000:
   who=w.identity();identities+=1;wins=tries=0
   # Every request counts toward the bound: abandonments raise the identity's
   # risk streak faster than it decays, so counting only assigned leases let a
   # cooled-down identity retry forever. On refusal, back off long enough for
   # risk to decay, as an attacker facing cooldowns would.
   while wins<G and tries<200:
    lease=w.request(who);tries+=1
    if lease.get('status')!='assigned':w.advance(1800);continue
    k=4 if acquire=='honest' else 1;payload={}
    for i,(t,seed) in enumerate(unit_keys(lease)):
     if i<k:
      if (t,seed) not in done:spent+=1;done.add((t,seed))
      payload[t]=(b'honest:'+t.encode(),'honest')
     else:payload[t]=(b'fabricated:'+t.encode(),'fabricated')
    w.advance(UNIT_S*k);ok,_=attempt(w,who,lease,payload,only_honest_drawn);wins+=ok
   if wins<G:continue
   try:w.c.grant_trust(who,allowance=10,ttl=3600)
   except ValueError:continue
   if acquire=='cached':w.advance(1800)  # let abandonment risk decay before use
   while fraud<TARGET:
    lease=w.request(who)
    if lease.get('status')!='assigned':break
    if lease.get('tier')!='trusted':w.advance(TTL+1);break
    t=lease['tasks'][0]['task'];ok,g=attempt(w,who,lease,{t:(b'fabricated:'+t.encode(),'fabricated')},submit_rule)
    if ok:fraud+=1;retained+=g
    if ok and policy=='deferred' and g==0:caught+=1;break
    w.advance(4)  # stay under the >3-requests-per-10s velocity penalty
  per=lambda x:x/fraud if fraud else None
  return {'fraudulent_admissions':fraud,'identities':identities,'identities_caught':caught,'work_units':spent,
          'discount':per(spent),'fabricated_units_retained_per_admission':per(retained),'replayed_units_per_admission':per(w.replayed)}
 finally:w.close()

def capacity_attack(verdicts,work,*,holders,duration=3600,honest_every=5):
 """Disappearing workers: fresh identities that take a lease and never return."""
 w=World(work,verdicts,capacity=16);served=refused=0;due=[0]*holders;busy=[]
 try:
  for t in range(duration):
   w.now[0]=float(t);keep=[]
   for end,job in busy:
    if end<=t:
     who,lease,outputs,ch=job;r=w.c.submit(lease['lease'],who,lease['binding'],ch['id'],outputs)
     if r['status']=='pending':w.audit(lease,outputs,{x:'honest' for x in outputs},ch)
    else:keep.append((end,job))
   busy=keep
   for i in range(holders):
    if due[i]<=t:r=w.request(w.identity());due[i]=t+TTL+1 if r.get('status')=='assigned' else t+5
   if t%honest_every==0:
    who=w.identity();lease=w.request(who)
    if lease.get('status')=='assigned':
     outputs={x['task']:b'honest:'+x['task'].encode() for x in lease['tasks']}
     ch=w.c.commit(lease['lease'],who,lease['binding'],w.c.output_root(lease['binding'],outputs))
     busy.append((t+7,(who,lease,outputs,ch)));served+=1
    else:refused+=1
  return {'holders':holders,'honest_arrivals':served+refused,'honest_refused':refused,'refusal_rate':refused/(served+refused),'attacker_work_units':0}
 finally:w.close()

def grid():
 """Every configuration, in reporting order, as (key, kind, parameters)."""
 out=[]
 for q in (1,2,4):
  for k in (0,1,2,3,4):
   for cap,cache in ((3,'reuse'),(3,'invalid'),(1,'reuse'),(16,'reuse')):
    out.append(({'tier':'bundle','q':q,'k':k,'cap':cap,'cache':cache,'deployed':(cap,cache)==(3,'reuse')},'bundle',dict(q=q,k=k,cap=cap,cache=cache)))
 out.append(({'tier':'bundle','q':1,'k':1,'cap':3,'cache':'reuse','strategy':'submit-regardless','deployed':True},'bundle',dict(q=1,k=1,adaptive=False)))
 for budget in (64000,128000):
  for mode in ('pool_only','pool_and_trace'):
   out.append(({'tier':'bundle','q':1,'partial_budget':budget,'commitment':mode,'cap':3,'deployed':mode=='pool_and_trace'},'bundle',dict(q=1,k=0,partial=(budget,mode))))
 for policy in ('immediate','deferred'):
  for p in (0.02,0.05,0.1,0.25):
   for G in (1,3,10):
    for acquire in ('honest','cached'):
     out.append(({'tier':'trusted','policy':policy,'p':p,'G':G,'acquire':acquire},'trusted',dict(policy=policy,p=p,G=G,acquire=acquire)))
 for holders in (0,4,8,12,16):out.append(({'tier':'capacity','holders':holders},'capacity',dict(holders=holders)))
 return out

def key(label):return json.dumps(label,sort_keys=True)

def run_one(item):
 """One configuration in its own process, database and verdict stream.

 The verdict stream is seeded from the configuration itself, so a result does
 not depend on which worker ran it or in what order.
 """
 label,kind,params=item
 rng=random.Random(int(hashlib.sha256((str(SEED)+key(label)).encode()).hexdigest()[:16],16))
 work=ROOT/'tmp/adversarial/phase2'/hashlib.sha256(key(label).encode()).hexdigest()[:12];work.mkdir(parents=True,exist_ok=True)
 fn={'bundle':bundle_attack,'trusted':trusted_attack,'capacity':capacity_attack}[kind]
 try:return {**label,**fn(Verdicts(rng),work,**params)}
 finally:shutil.rmtree(work,ignore_errors=True)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 manifest={'protocol':digest(PROTOCOL),'runner':digest(Path(__file__)),'phase1':digest(PHASE1),
  'scheduler':{f:digest(ROOT/'research'/f) for f in ('pool_admission.py','adaptive_admission.py','vina_pool_campaign.py','docking_campaign.py','whole_run_campaign.py')},
  'target_admissions':TARGET,'verdict_seed':SEED,'unit_seconds':UNIT_S,'give_up_after_attempts_without_admission':GIVE_UP,'workers':WORKERS,
  'note':'Scheduler challenge randomness is the unmodified system CSPRNG; verdict resampling is seeded per configuration.'}
 mp=OUT/'phase2_manifest.json'
 if mp.exists():
  frozen=json.loads(mp.read_text())
  if frozen!=manifest:
   # A runner change is accepted only with a recorded revision naming the new
   # hash; every other pinned input must still match exactly.
   revisions=json.loads((OUT/'phase2_revisions.json').read_text()) if (OUT/'phase2_revisions.json').exists() else []
   same_inputs={k:v for k,v in frozen.items() if k!='runner'}=={k:v for k,v in manifest.items() if k!='runner'}
   assert same_inputs and any(r['runner']==manifest['runner'] for r in revisions),'Immutable manifest changed without a recorded revision: '+str(mp)
 else:mp.write_text(json.dumps(manifest,indent=2))
 ledger=OUT/'phase2.jsonl';items=grid();order={key(i[0]):n for n,i in enumerate(items)}
 # Each row carries its configuration key, so a restart skips finished work.
 recorded=[json.loads(s) for s in ledger.read_text().splitlines() if s.strip()] if ledger.exists() else []
 done={r['config_key'] for r in recorded}
 todo=[i for i in items if key(i[0]) not in done]
 print('configurations: %d total, %d already recorded, %d to run'%(len(items),len(done),len(todo)),flush=True)
 with ProcessPoolExecutor(max_workers=WORKERS) as pool:
  futures={pool.submit(run_one,i):key(i[0]) for i in todo}
  for f in as_completed(futures):
   r={'config_key':futures[f],**f.result()}
   with ledger.open('a') as h:
    h.write(json.dumps(r)+chr(10));h.flush();os.fsync(h.fileno())
   print(json.dumps(r),flush=True)
 rows=sorted((json.loads(s) for s in ledger.read_text().splitlines() if s.strip()),key=lambda r:order[r['config_key']])
 (OUT/'phase2.json').write_text(json.dumps(rows,indent=2));print('PHASE2 COMPLETE',len(rows),'rows',flush=True)

if __name__=='__main__':main()
