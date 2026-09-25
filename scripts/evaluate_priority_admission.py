"""Amendment 9: price newcomer admission under an explicit attacker CPU budget.

Queue, eviction, ordering, claims, tickets and commitments run the real
prototype code (research/ticket_admission.py, research/priority_admission.py).
Arrivals, the 1.52 s replay and all puzzle costs are simulated. Puzzle costs are
accounted from measured hash rates rather than executed: honest phones at their
measured JavaScript rates, the attacker at the measured native rate per core
under load. Proof verification is therefore replaced by accounting here; the
real verification path is covered by research/tests/test_priority_admission.py.
"""
import hashlib,json,math,os,random,secrets,shutil,statistics,sys,tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.ticket_admission import TicketAdmission,encoded
from research.priority_admission import PriorityAdmission
from scripts.admission_replay_clock import ReplayClock

OUT=ROOT/'local-research/priority-admission-2026-09-24'
PROTOCOL=ROOT/'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'
SPEC={'campaign':'fixture','input_hashes':['fixture-only'],'max_evals':256000}
DT=0.25;ARRIVE_S=240;DRAIN_S=150;REPLAY_S=1.52;PATIENCE_S=10;TTL=120
HONEST_EVERY_S=2          # 0.5 newcomers per second
CORE_RATE=1.25e6          # measured native hashes/s per core under load
DEVICES={'budget':34866,'mid':148840,'flagship':181994}  # measured JS hashes/s
SUB_BITS=10;SUB_HASHES=2**SUB_BITS
ATTACK_CAP_PER_TICK=30    # at most 120 fake submissions per second; the issuer bursts at 32
HONEST_MARGIN=1.25;ATTACK_MARGIN=1.5

class SimFixed(TicketAdmission):
 """Prototype FIFO puzzle; the proof is accounted, not executed."""
 def _proof(self,t,root,proof):return bool(proof and proof.get('accounted_ok'))
 def claim(self,tier):
  with self.db() as db:
   self._expire(db);r=db.execute("SELECT * FROM queue WHERE state='QUEUED' AND tier=? ORDER BY issued,id LIMIT 1",(tier,)).fetchone()
   if not r:return None
   db.execute("UPDATE queue SET state='AUDITING' WHERE id=?",(r['id'],));return dict(r)
 def finish(self,identity,verdict,store):
  with self.db() as db:
   self._expire(db);r=db.execute("SELECT * FROM queue WHERE id=? AND state='AUDITING'",(identity,)).fetchone()
   if not r or r['root']!=verdict[0]:raise ValueError('Bound verdict required')
   db.execute('UPDATE queue SET state=?,payload=NULL WHERE id=?',('GRANTED' if verdict[1] else 'FAILED',identity))

class SimPriority(PriorityAdmission):
 def effort_of(self,t,root,proof):return int(proof['accounted']) if proof and 'accounted' in proof else 0

def run(item, exact_replay=False):
 mech,workers,cores,seed=item[:4];strategy=item[4] if len(item)>4 else 'follow';rng=random.Random(seed);now=[0.0]
 work=Path(tempfile.mkdtemp(dir=ROOT/'tmp'));key=secrets.token_bytes(32)
 kw=dict(clock=lambda:now[0],capacity=16,issuance_rate=1e9,ttl=TTL)
 c=SimPriority(work/'q.sqlite',key,SPEC,sub_bits=SUB_BITS,**kw) if mech=='priority' else SimFixed(work/'q.sqlite',key,SPEC,puzzle_bits=16 if mech=='fixed16' else 18,**kw)
 bits=None if mech=='priority' else c.bits
 honest={};scheduled=[];inflight=[];budget=0.0;n=0;h=0
 att=dict(submitted=0,queued=0,replayed=0,hashes=0.0)
 classes=list(DEVICES)
 def new_ticket(owner,good):
  t=c.issue(owner)
  if t['status']!='ticket':return None
  body=encoded({str(s):('honest' if good else 'fake') for s in t['assignment']['seeds']});return t,body,hashlib.sha256(body).hexdigest()
 def finish_replay(row):
  payload=json.loads(row['payload']);good=payload[next(iter(payload))]=='honest'
  try:c.finish(row['id'],(row['root'],good),lambda db,r:None)
  except ValueError:return
  if good and row['id'] in honest:honest[row['id']]['outcome']='granted';honest[row['id']]['wait']=now[0]-honest[row['id']]['arrived']
  elif not good:att['replayed']+=1
 service=ReplayClock(now,inflight,workers,REPLAY_S,lambda:c.claim('new'),finish_replay)
 try:
  for tick in range(int((ARRIVE_S+DRAIN_S)/DT)):
   if exact_replay:service.advance(tick*DT)
   else:now[0]=tick*DT
   arriving=now[0]<ARRIVE_S
   # Verifier: finish due replays, then claim up to `workers` newcomer submissions.
   for job in [j for j in inflight if not exact_replay and j[0]<=now[0]]:
    inflight.remove(job);finish_replay(job[1])
   while not exact_replay and len(inflight)<workers:
    r=c.claim('new')
    if not r:break
    inflight.append((now[0]+REPLAY_S,r))
   # Honest newcomers: one every 2 s, cycling device classes.
   if arriving and tick%int(HONEST_EVERY_S/DT)==0:
    # Honest arrivals have their own counter so classes stay balanced.
    h+=1;n+=1;cls=classes[h%3];rate=DEVICES[cls];owner='honest-%d'%n;issued=new_ticket(owner,True)
    rec=dict(cls=cls,arrived=now[0],paid_s=0.0,outcome='denied')
    if issued is None:honest['unissued-'+owner]=rec
    else:
     t,body,root=issued;o=c.offer(t['ticket'],root,owner);proof=None
     if o['status']=='effort':
      # 'follow' bids just above the suggestion; 'patience' bids the full 10 s (amendment 9b).
      cap=max(1,int(rate*PATIENCE_S/SUB_HASHES));pay=cap if strategy=='patience' else min(cap,max(1,math.ceil(o['suggested']*HONEST_MARGIN)))
      rec['paid_s']=rng.gammavariate(pay,SUB_HASHES)/rate;proof={'accounted':pay};rec['bid']=pay;rec['capped']=pay==cap
     elif o['status']=='puzzle':
      rec['paid_s']=rng.expovariate(1/2**bits)/rate;proof={'accounted_ok':True}
     scheduled.append((now[0]+rec['paid_s'],t,body,root,owner,proof,rec))
   for item in [s for s in scheduled if s[0]<=now[0]]:
    scheduled.remove(item);_,t,body,root,owner,proof,rec=item
    r=c.submit(t['ticket'],root,body,owner,proof);rec['submit']=r['status']
    if r['status']=='queued':honest[r['id']]=rec
    else:honest['refused-'+owner]=rec
   # Attacker best response: fakes outbidding the published suggestion, within budget.
   if cores and arriving:
    budget+=cores*CORE_RATE*DT
    for _ in range(ATTACK_CAP_PER_TICK):
     n+=1;owner='attacker-%d'%n;issued=new_ticket(owner,False)
     if issued is None:break
     t,body,root=issued;o=c.offer(t['ticket'],root,owner)
     if o['status']=='ready':cost=0;proof=None
     elif o['status']=='effort':pay=math.ceil(max(1,o['suggested'])*ATTACK_MARGIN)+1;cost=pay*SUB_HASHES;proof={'accounted':pay}
     else:cost=2**bits;proof={'accounted_ok':True}
     if cost>budget:break
     budget-=cost;att['hashes']+=cost;att['submitted']+=1
     if c.submit(t['ticket'],root,body,owner,proof)['status']=='queued':att['queued']+=1
   if exact_replay:service.fill()
   if not arriving and not inflight and not scheduled:break
  # Anything still queued or auditing at the end counts as not served.
  per={}
  for cls in classes:
   rs=[r for r in honest.values() if r['cls']==cls];paid=[r['paid_s'] for r in rs]
   per[cls]=dict(arrivals=len(rs),granted=sum(r['outcome']=='granted' for r in rs),
                 served=sum(r['outcome']=='granted' for r in rs)/len(rs) if rs else None,
                 paid_s_median=statistics.median(paid) if paid else None,paid_s_p95=sorted(paid)[int(.95*(len(paid)-1))] if paid else None,
                 paid_any=sum(p>0 for p in paid),capped=sum(bool(r.get('capped')) for r in rs))
  return dict(mechanism=mech,honest_strategy=strategy,workers=workers,attacker_cores=cores,seed=seed,classes=per,attacker=att,
              attacker_hashes_per_s=att['hashes']/ARRIVE_S,
              timing=service.metrics() if exact_replay else {'mode':'legacy-tick'})
 finally:shutil.rmtree(work,ignore_errors=True)

def main():
 strategy=sys.argv[1] if len(sys.argv)>1 else 'follow'
 if strategy not in ('follow','patience'):raise ValueError('Strategy')
 # The original grid keeps its directory; the amendment 9b follow-up gets its own.
 out=OUT if strategy=='follow' else OUT.parent/(OUT.name+'-patience');out.mkdir(parents=True,exist_ok=True)
 digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 manifest=dict(protocol=digest(PROTOCOL),runner=digest(Path(__file__)),prototype=digest(ROOT/'research/ticket_admission.py'),
  mechanism=digest(ROOT/'research/priority_admission.py'),devices=DEVICES,core_rate=CORE_RATE,replay_s=REPLAY_S,patience_s=PATIENCE_S,
  honest_per_s=1/HONEST_EVERY_S,sub_bits=SUB_BITS,arrive_s=ARRIVE_S,honest_margin=HONEST_MARGIN,attack_margin=ATTACK_MARGIN,
  honest_strategy=strategy,note='Queue code real; arrivals, replay time and puzzle costs simulated and accounted from measured rates.')
 mp=out/'manifest.json'
 if mp.exists():assert json.loads(mp.read_text())==manifest,'Immutable manifest changed'
 else:mp.write_text(json.dumps(manifest,indent=2))
 if strategy=='patience':grid=[('priority',w,c,20260924,'patience') for w in (1,2,4,8) for c in (0,0.1,0.25,1,4,16)]
 else:grid=[(m,w,c,20260924) for m in ('fixed16','fixed18','priority') for w in (1,2,4,8) for c in (0,0.1,0.25,1,4,16)]
 ledger=out/'results.jsonl';done={(r['mechanism'],r['workers'],r['attacker_cores']) for r in (json.loads(s) for s in ledger.read_text().splitlines() if s.strip())} if ledger.exists() else set()
 todo=[g for g in grid if g[:3] not in done];print('runs: %d total, %d to run'%(len(grid),len(todo)),flush=True)
 with ProcessPoolExecutor(max_workers=12) as pool:
  for r in pool.map(run,todo):
   with ledger.open('a') as h:h.write(json.dumps(r)+chr(10));h.flush();os.fsync(h.fileno())
   print(r['mechanism'],r['workers'],r['attacker_cores'],{k:round(v['served'],2) if v['served'] is not None else None for k,v in r['classes'].items()},flush=True)
 print('PRIORITY ADMISSION COMPLETE',flush=True)

if __name__=='__main__':main()
