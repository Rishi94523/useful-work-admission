"""Real scheduler retry grinding with a fixed correctness mask.

Molecular replay outcomes are supplied by the model here, not recomputed in this
experiment. Separate audits.json contains actual full molecular replay attacks.
"""
import hashlib,json,math,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
from research.docking_campaign import Campaign
from research.whole_run_campaign import WholeRunCampaign
rows=[]
with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
 for guarded in [False,True]:
  c=WholeRunCampaign(Path(d)/'guarded.sqlite') if guarded else Campaign(Path(d)/'legacy.sqlite')
  if guarded:c.register('test','engine','maps','ligand','input','box',0,64,4000,64)
  else:c.add('test',{'model_version':'engine','receptor':'maps','ligand':'ligand','conformer_bank':'input','region':'box','search_parameters':{'cap':4000}},0,64,64)
  attempts=[]
  # k=32 solved runs are cached once; each new lease changes only commitment.
  for attempt in range(10000):
   owner='new-owner-'+str(attempt)
   try:lease=c.lease('test',owner)
   except LookupError:break
   commitment=hashlib.sha256((lease['binding']+'fixed partial cache').encode()).hexdigest();ch=c.commit(lease['lease'],owner,lease['binding'],commitment,8)
   accepted=all(i<32 for _,i in ch['draws'])
   c.finish(lease['lease'],owner,lease['binding'],ch['id'],commitment,accepted,{'model_only':True})
   attempts.append({'attempt':attempt+1,'draws':ch['draws'],'accepted':accepted})
   if accepted:break
  rows.append({'guarded':guarded,'cached_correct_units':32,'assigned_units':64,'audit_q':8,'additional_science_per_retry':0,'attempts':attempts,'accepted':any(x['accepted'] for x in attempts),'recovery_queue':c.recovery_queue() if guarded else None})
bounds=[]
for q in [4,8,16,32]:
 for k in [6,16,32,48,57,63]:
  p=math.comb(k,q)/math.comb(64,q) if k>=q else 0
  for budget in [1,3]:
   cumulative=1-(1-p)**budget
   bounds.append({'q':q,'correct_units':k,'total':64,'max_credit_challenges':budget,'per_attempt_probability':p,'probability_with_fixed_partial_cache':cumulative,'relative_science_per_success_across_new_cohorts':(k/64)/cumulative if cumulative else None})
out={'scope':'Actual SQLite leases, commitments, CSPRNG challenges and credits, with verification acceptance computed from a fixed known mask. This is a retry-policy attack, not a molecular timing benchmark. Cache built once; replaying failed assignments incurs no new science in this model.','runs':rows,'conditional_bounds':bounds,'limitation':'A global challenge cap limits rerolls but creates denial-of-work-pool/recovery risk. Admission and outstanding-lease budgets are still required. Bounds assume fixed cached correctness coverage and no adaptive correct-output shortcuts.'}
(OUT/'retry_attack.json').write_text(json.dumps(out,indent=2)+'\n');print([{'guarded':x['guarded'],'attempts':len(x['attempts']),'accepted':x['accepted']} for x in rows])
