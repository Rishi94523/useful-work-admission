"""Amendment 10: an attested-newcomer lane under CPU and attestation budgets.

Queue, lanes, eviction, ordering, tickets, token checks and nullifiers run the
real prototype code (research/attested_admission.py and the modules beneath
it). As in amendment 9b, arrivals, the 1.52 s replay and all puzzle costs are
simulated and accounted from measured hash rates, and honest anonymous
newcomers under pressure bid their full 10 s of patience. MockAttester stands
in for the token issuer. E1 ('oneshot') repeats the amendment 9 arrival
process; E2 ('bootstrap') keeps each honest newcomer contributing until three
bundles are granted, the trust threshold.
"""
import hashlib,json,math,os,random,secrets,shutil,statistics,sys,tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.ticket_admission import encoded
from research.attested_admission import AttestedAdmission,MockAttester
from scripts.admission_replay_clock import ReplayClock
from scripts.evaluate_priority_admission import (DT,ARRIVE_S,DRAIN_S,REPLAY_S,PATIENCE_S,TTL,HONEST_EVERY_S,CORE_RATE,
  DEVICES,SUB_BITS,SUB_HASHES,ATTACK_CAP_PER_TICK,ATTACK_MARGIN,SPEC)

OUT=ROOT/'local-research/attested-admission-2026-09-25'
PROTOCOL=ROOT/'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'
ORIGIN='https://admission.example'
TRUST_BUNDLES=3
WORK_S={'budget':4*7.55,'mid':4*2.02,'flagship':4*2.04}  # four units at each device's measured median

class SimAttested(AttestedAdmission):
 def effort_of(self,t,root,proof):return int(proof['accounted']) if proof and 'accounted' in proof else 0

def attested_flags(n,share):
 """Exactly `share` of each class's first n users carry a token, spread evenly."""
 return [int((k+1)*share+1e-9)>int(k*share+1e-9) for k in range(n)]

def run(item, exact_replay=False):
 exp,workers,cores,share,arate,seed=item;rng=random.Random(seed);now=[0.0];clock=lambda:now[0]
 work=Path(tempfile.mkdtemp(dir=ROOT/'tmp'))
 issuer=MockAttester(ORIGIN,per_device=10,window_s=3600,clock=clock)
 c=SimAttested(work/'q.sqlite',secrets.token_bytes(32),SPEC,clock=clock,capacity=16,issuance_rate=1e9,ttl=TTL,
               sub_bits=SUB_BITS,verify_attestation=issuer.verify)
 total=ARRIVE_S+DRAIN_S;attack_until=ARRIVE_S if exp=='oneshot' else total
 classes=list(DEVICES);flags={k:attested_flags(200,share) for k in classes};seen={k:0 for k in classes}
 users=[];owners={};scheduled=[];inflight=[];budget=0.0;tokens=0.0;n=0;h=0;farm=0
 att=dict(submitted=0,queued=0,replayed=0,hashes=0.0,attested_sent=0,attested_queued=0,attested_replayed=0)
 def body_for(t,good):
  body=encoded({str(s):('honest' if good else 'fake') for s in t['assignment']['seeds']});return body,hashlib.sha256(body).hexdigest()
 def fail(u):
  u['pending']=None
  if exp=='oneshot':u['done']=True
  else:u['next_at']=now[0]+WORK_S[u['cls']]
 def anonymous(u,owner):
  t=c.issue(owner);body,root=body_for(t,True);o=c.offer(t['ticket'],root,owner);proof=None;paid=0.0
  if o['status']=='effort':
   pay=max(1,int(DEVICES[u['cls']]*PATIENCE_S/SUB_HASHES));paid=rng.gammavariate(pay,SUB_HASHES)/DEVICES[u['cls']];proof={'accounted':pay}
  u['paid_s'].append(paid);u['pending']='scheduled';scheduled.append((now[0]+paid,u,t,body,root,owner,proof))
 def attempt(u):
  u['attempts']+=1;owner='honest-%d-%d'%(u['id'],u['attempts'])
  if u['attested']:
   t=c.issue(owner,attestation=issuer.token('device-%d'%u['id']))
   if t['status']=='ticket':
    body,root=body_for(t,True);c.offer(t['ticket'],root,owner);r=c.submit(t['ticket'],root,body,owner)
    if r['status']=='queued':u['pending']=r['id'];owners[r['id']]=u;u['lanes'].append('attested');return
   u['fallbacks']+=1  # attested lane full: fall back to bidding
  u['lanes'].append('anonymous');anonymous(u,owner)
 def finish_replay(row):
  payload=json.loads(row['payload']);good=payload[next(iter(payload))]=='honest'
  try:c.finish(row['id'],(row['root'],good),lambda db,r:None)
  except ValueError:return
  u=owners.pop(row['id'],None)
  if good and u:
   u['grants']+=1;u['pending']=None;u.setdefault('first_grant',now[0]-u['arrived'])
   if exp=='oneshot' or u['grants']>=TRUST_BUNDLES:u['done']=True;u['trusted_at']=now[0]-u['arrived']
   else:u['next_at']=now[0]+WORK_S[u['cls']]
  elif not good:
   att['replayed']+=1
   if row['tier']=='attested':att['attested_replayed']+=1
 service=ReplayClock(now,inflight,workers,REPLAY_S,c.next_newcomer,finish_replay)
 try:
  for tick in range(int(total/DT)):
   if exact_replay:service.advance(tick*DT)
   else:now[0]=tick*DT
   arriving=now[0]<ARRIVE_S;attacking=now[0]<attack_until
   for job in [j for j in inflight if not exact_replay and j[0]<=now[0]]:
    inflight.remove(job);finish_replay(job[1])
   while not exact_replay and len(inflight)<workers:
    r=c.next_newcomer()
    if not r:break
    inflight.append((now[0]+REPLAY_S,r))
   if arriving and tick%int(HONEST_EVERY_S/DT)==0:
    h+=1;n+=1;cls=classes[h%3];a=flags[cls][seen[cls]];seen[cls]+=1
    users.append(dict(id=n,cls=cls,attested=a,arrived=now[0],next_at=now[0],pending=None,done=False,grants=0,
                      attempts=0,fallbacks=0,paid_s=[],lanes=[]))
   for u in users:
    if not u['done'] and u['pending'] is None and u['next_at']<=now[0]:attempt(u)
   for item in [s for s in scheduled if s[0]<=now[0]]:
    scheduled.remove(item);_,u,t,body,root,owner,proof=item
    r=c.submit(t['ticket'],root,body,owner,proof)
    if r['status']=='queued':u['pending']=r['id'];owners[r['id']]=u
    else:fail(u)
   if tick%4==0:  # evicted or expired submissions are lost
    for u in users:
     if isinstance(u['pending'],str) and u['pending']!='scheduled' and c.state(u['pending']) in (None,'EVICTED'):
      owners.pop(u['pending'],None);fail(u)
   if attacking and arate:
    tokens+=arate*DT
    while tokens>=1:
     tokens-=1;farm+=1;n+=1;owner='attacker-%d'%n;t=c.issue(owner,attestation=issuer.token('farm-%d'%farm))
     body,root=body_for(t,False);c.offer(t['ticket'],root,owner);att['attested_sent']+=1
     if c.submit(t['ticket'],root,body,owner)['status']=='queued':att['attested_queued']+=1
   if cores and attacking:
    budget+=cores*CORE_RATE*DT
    for _ in range(ATTACK_CAP_PER_TICK):
     n+=1;owner='attacker-%d'%n;t=c.issue(owner)
     if t['status']!='ticket':break
     body,root=body_for(t,False);o=c.offer(t['ticket'],root,owner)
     if o['status']=='ready':cost=0;proof=None
     else:pay=math.ceil(max(1,o['suggested'])*ATTACK_MARGIN)+1;cost=pay*SUB_HASHES;proof={'accounted':pay}
     if cost>budget:break
     budget-=cost;att['hashes']+=cost;att['submitted']+=1
     if c.submit(t['ticket'],root,body,owner,proof)['status']=='queued':att['queued']+=1
   if exact_replay:service.fill()
   if exp=='oneshot' and not arriving and not inflight and not scheduled:break
  groups={}
  for cls in classes:
   for lane,flag in (('attested',True),('anonymous',False)):
    rs=[u for u in users if u['cls']==cls and u['attested']==flag]
    if not rs:continue
    paid=[p for u in rs for p in u['paid_s']];trust=[u['trusted_at'] for u in rs if u['grants']>=TRUST_BUNDLES]
    groups[cls+'/'+lane]=dict(users=len(rs),served=sum(u['grants']>0 for u in rs)/len(rs),
      trusted=sum(u['grants']>=TRUST_BUNDLES for u in rs)/len(rs) if exp=='bootstrap' else None,
      trust_s_median=statistics.median(trust) if trust and exp=='bootstrap' else None,
      attempts=sum(u['attempts'] for u in rs),fallbacks=sum(u['fallbacks'] for u in rs),
      puzzle_s_median=statistics.median(paid) if paid else 0.0,puzzle_s_total=sum(paid))
  return dict(experiment=exp,workers=workers,attacker_cores=cores,attested_share=share,attacker_tokens_per_s=arate,seed=seed,
              groups=groups,attacker=att,attacker_hashes_per_s=att['hashes']/attack_until,
              timing=service.metrics() if exact_replay else {'mode':'legacy-tick'})
 finally:shutil.rmtree(work,ignore_errors=True)

def grid(exp):
 if exp=='oneshot':return [(exp,w,cr,s,a,20260925) for w in (2,8) for cr in (0,1,4,16) for s in (0,0.5,0.9) for a in (0,0.1,1,10)]
 return [(exp,w,cr,s,a,20260925) for w in (4,8) for cr in (0,16) for s in (0,0.9) for a in (0,0.1,1,10)]

def main():
 exp=sys.argv[1] if len(sys.argv)>1 else 'oneshot'
 if exp not in ('oneshot','bootstrap'):raise ValueError('Experiment')
 out=OUT/exp;out.mkdir(parents=True,exist_ok=True)
 digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 manifest=dict(protocol=digest(PROTOCOL),runner=digest(Path(__file__)),base_runner=digest(ROOT/'scripts/evaluate_priority_admission.py'),
  prototype=digest(ROOT/'research/ticket_admission.py'),priority=digest(ROOT/'research/priority_admission.py'),
  mechanism=digest(ROOT/'research/attested_admission.py'),devices=DEVICES,work_s=WORK_S,core_rate=CORE_RATE,replay_s=REPLAY_S,
  patience_s=PATIENCE_S,honest_per_s=1/HONEST_EVERY_S,trust_bundles=TRUST_BUNDLES,experiment=exp,
  note='Queue and token code real; arrivals, replay time and puzzle costs simulated and accounted; MockAttester stands in for the issuer.')
 mp=out/'manifest.json'
 if mp.exists():assert json.loads(mp.read_text())==manifest,'Immutable manifest changed'
 else:mp.write_text(json.dumps(manifest,indent=2))
 ledger=out/'results.jsonl'
 done={(r['workers'],r['attacker_cores'],r['attested_share'],r['attacker_tokens_per_s']) for r in (json.loads(s) for s in ledger.read_text().splitlines() if s.strip())} if ledger.exists() else set()
 todo=[g for g in grid(exp) if g[1:5] not in done];print('runs: %d total, %d to run'%(len(grid(exp)),len(todo)),flush=True)
 with ProcessPoolExecutor(max_workers=12) as pool:
  for r in pool.map(run,todo):
   with ledger.open('a') as fh:fh.write(json.dumps(r)+chr(10));fh.flush();os.fsync(fh.fileno())
   key='trusted' if exp=='bootstrap' else 'served'
   print(r['workers'],r['attacker_cores'],r['attested_share'],r['attacker_tokens_per_s'],{k:round(v[key],2) for k,v in r['groups'].items()},flush=True)
 print('ATTESTED ADMISSION COMPLETE',flush=True)

if __name__=='__main__':main()
