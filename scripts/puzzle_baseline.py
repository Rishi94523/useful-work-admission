"""Hashcash baseline under the same accounting as the useful-work evaluation.

The puzzle asks for a nonce such that SHA-256(challenge || nonce) has k leading
zero bits. Expected client work is 2^k hashes; verification is one hash; a fresh
server challenge makes precomputation useless. These are exactly the properties
useful work gives up, so this baseline states the price being paid.

Calibration is native against native. The Vina units under evaluation run as a
native executable, so the puzzle is solved natively too; browser-against-browser
comparison belongs to the device study. The difficulty k is set so the median
solve time matches the median honest unit time measured in phase 1 under the
same four-worker load, not chosen by hand.
"""
import hashlib,json,math,os,secrets,statistics,sys,time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'local-research/adversarial-2026-09-23'
PHASE1=OUT/'phase1.jsonl'
SOLVES=240
WORKERS=4

def leading_zero_bits(d):
 bits=0
 for b in d:
  if b==0:bits+=8;continue
  return bits+8-b.bit_length()
 return bits

def solve(args):
 challenge,k=args;nonce=0;begin=time.perf_counter()
 while True:
  if leading_zero_bits(hashlib.sha256(challenge+nonce.to_bytes(8,'little')).digest())>=k:
   return {'k':k,'nonce':nonce,'hashes':nonce+1,'ms':(time.perf_counter()-begin)*1000}
  nonce+=1

def hash_rate(seconds=3.0):
 c=secrets.token_bytes(16);n=0;end=time.perf_counter()+seconds
 while time.perf_counter()<end:
  hashlib.sha256(c+n.to_bytes(8,'little')).digest();n+=1
 return n/seconds

def verify_cost_us(trials=20000):
 c=secrets.token_bytes(16);begin=time.perf_counter()
 for n in range(trials):leading_zero_bits(hashlib.sha256(c+n.to_bytes(8,'little')).digest())
 return (time.perf_counter()-begin)/trials*1e6

def pct(xs,p):
 s=sorted(xs);return s[min(len(s)-1,int(p*len(s)))]

def main():
 rows=[json.loads(s) for s in PHASE1.read_text().splitlines() if s.strip()]
 honest=[r['replay_ms'] for r in rows if r.get('attack')=='honest' and r.get('accepted')]
 assert honest,'Phase 1 honest timings missing; run adversarial_replay_eval.py first'
 target=statistics.median(honest)
 # Rate under the same four-way load the useful-work units were timed under.
 with ProcessPoolExecutor(max_workers=WORKERS) as pool:rate=statistics.median(pool.map(hash_rate,[3.0]*WORKERS))
 # Median of a geometric count with success probability 2^-k is about ln2 * 2^k.
 k=max(1,round(math.log2(target/1000*rate/math.log(2))))
 with ProcessPoolExecutor(max_workers=WORKERS) as pool:
  solves=list(pool.map(solve,[(secrets.token_bytes(16),k) for _ in range(SOLVES)]))
 ms=[s['ms'] for s in solves]
 unit=honest
 result={
  'calibration':{'target_median_unit_ms':target,'hash_rate_per_s_under_load':rate,'difficulty_bits':k,'solves':SOLVES,'workers':WORKERS},
  'puzzle_client_ms':{'median':statistics.median(ms),'p95':pct(ms,.95),'p99':pct(ms,.99),'max':max(ms),'cv':statistics.pstdev(ms)/statistics.mean(ms)},
  'useful_unit_client_ms':{'median':statistics.median(unit),'p95':pct(unit,.95),'p99':pct(unit,.99),'max':max(unit),'cv':statistics.pstdev(unit)/statistics.mean(unit)},
  'puzzle_verify_us':verify_cost_us(),
  'note':'Native against native. Unit client cost is honest replay time, which is a re-execution of the client computation under identical load.'}
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/'puzzle_baseline.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))

if __name__=='__main__':main()
