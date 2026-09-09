"""Separate observed browser economics, policy simulations and analytic bounds."""
import gzip,hashlib,json,math,statistics
from collections import Counter
from pathlib import Path
OUT=Path('docs/evaluation/adaptive_docking_2026-09-08')
def stats(values):
 v=[float(x) for x in values if x is not None]
 return {'n':len(v),'median':statistics.median(v),'min':min(v),'max':max(v),'mean':statistics.mean(v)} if v else None
def rate_interval(k,n):
 if not n:return None
 z=1.96;p=k/n;den=1+z*z/n;mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
 return [max(0,mid-half),min(1,mid+half)]
def summarize_rows(rows):
 result={}
 for tier in ['low','medium','high']:
  group=[r for r in rows if r['decision'].get('tier')==tier and 'client' in r];fields={}
  for field in ['molecular_ms','ligand_init_ms','commit_ms','total_ms','heap_bytes','science_bytes','commitment_bytes','new_runs']:
   fields['client_'+field]=stats([r['client'].get(field) for r in group])
  for field in ['molecular_ms','ligand_init_ms','total_ms','heap_bytes','opening_bytes']:
   fields['server_'+field]=stats([r['server'].get(field) for r in group])
  for field in ['admission_and_scheduler_ms','challenge_db_ms','finish_db_ms','client_ipc_wall_ms','server_ipc_wall_ms']:
   fields[field]=stats([r.get(field) for r in group])
  derived=[]
  for r in group:
   c,s=r['client'],r['server'];warm=c['total_ms']-c['ligand_init_ms'];db=sum(r[k] for k in ['admission_and_scheduler_ms','challenge_db_ms','finish_db_ms'])
   risk=r['decision'].get('risk_processing_ms');finish_risk=r['outcome'].get('risk_processing_ms');risk=risk+finish_risk if risk is not None and finish_risk is not None else None
   derived.append({'warm_molecular_fraction':c['molecular_ms']/warm,'full_molecular_fraction':c['molecular_ms']/c['total_ms'],'client_warm_ms':warm,'client_other_ms':c['total_ms']-c['molecular_ms']-c['ligand_init_ms']-c['commit_ms'],'server_other_ms':s['total_ms']-s['molecular_ms']-s['ligand_init_ms'],'client_to_server_molecular_ratio':c['molecular_ms']/s['molecular_ms'] if s['molecular_ms'] else None,'client_to_server_full_ratio':c['total_ms']/(r.get('server_ipc_wall_ms',s['total_ms'])+db),'total_server_with_db_ms':r.get('server_ipc_wall_ms',s['total_ms'])+db,'database_and_scheduler_total_ms':db,'risk_logic_with_sql_ms':risk,'remaining_db_and_scheduler_ms':db-risk if risk is not None else None,'protocol_upload_bytes':c['commitment_bytes']+s['opening_bytes'],'science_collection_upload_bytes':c['science_bytes'],'assigned_manifest_bytes':len(json.dumps(r['units'],separators=(',',':')).encode())})
  if derived:
   for k in derived[0]:fields[k]=stats([r[k] for r in derived])
  result[tier]=fields
 return result
live={}
for filename in ['adaptive_loop.json','adaptive_loop_calibrated.json']:
 if not (OUT/filename).exists():continue
 data=json.loads((OUT/filename).read_text());scenarios=[]
 for s in data['scenarios']:
  attempts=[r for r in s['rows'] if 'client' in r];accepted=[r for r in attempts if r['outcome']['accepted']];cost=sum(r['client']['molecular_ms'] for r in attempts)
  scenarios.append({'name':s['name'],'fraction':s['fraction'],'assignments':len(attempts),'accepted':len(accepted),'terminal_status':s['rows'][-1]['decision']['status'],'tiers':dict(Counter(r['decision']['tier'] for r in attempts)),'molecular_ms':cost,'client_total_ms':sum(r['client']['total_ms'] for r in attempts),'historical_new_runs':sum(r['client']['new_runs'] for r in attempts),'credited_provisional_runs':sum(len(r['units']) for r in accepted),'known_correct_records_in_accepted_bundles':sum(r['client']['correct_records'] for r in accepted),'observed_molecular_ms_per_accept':cost/len(accepted) if accepted else None,'sequence':[{'tier':r['decision']['tier'],'risk_before':r['decision']['risk'],'risk_after':r['outcome']['risk'],'accepted':r['outcome']['accepted'],'conditional_pass_probability':math.comb(r['client']['correct_records'],r['decision']['q'])/math.comb(len(r['units']),r['decision']['q']) if r['client']['correct_records']>=r['decision']['q'] else 0} for r in attempts]})
 rows=[r for s in data['scenarios'] if s['name'] in ['honest','valid-spam'] for r in s['rows']]
 live[filename]={'scope':data['scope'],'client_init':data['client_init'],'server_init':data['server_init'],'honest_and_valid_tiers':summarize_rows(rows),'scenarios':scenarios}
cached=None
if (OUT/'cached_tier_economics.json').exists():
 c=json.loads((OUT/'cached_tier_economics.json').read_text());cached={'scope':c['scope'],'client_init':c['client_init'],'server_init':c['server_init'],'tiers':summarize_rows(c['rows'])}
simulations={}
for filename in ['policy_simulation.json','policy_simulation_calibrated.json']:
 if not (OUT/filename).exists():continue
 d=json.loads((OUT/filename).read_text());groups={}
 for s in d['scenarios']:
  key=s['scenario']+':'+str(s['fraction']);groups.setdefault(key,[]).append(s)
 summaries=[]
 for key,g in groups.items():
  accepts=sum(s['accepted'] for s in g);attempts=sum(sum(isinstance(r.get('outcome'),dict) for r in s['rows']) for s in g);cost=sum(s['modeled_total_molecular_ms'] for s in g)
  summaries.append({'scenario':key,'trajectories':len(g),'accepts':accepts,'challenged_attempts':attempts,'trajectories_with_credit':sum(s['accepted']>0 for s in g),'modeled_molecular_ms':cost,'modeled_ms_per_credit':cost/accepts if accepts else None,'terminal_states':dict(Counter(s['rows'][-1]['status'] for s in g))})
 simulations[filename]={'scope':d['scope'],'summaries':summaries}
bounds=[];rng=__import__('random').Random(104729)
for n,q in [(16,4),(64,8),(256,8)]:
 for f in [.1,.25,.5,.75,.9]:
  k=math.floor(n*f);p=math.comb(k,q)/math.comb(n,q) if k>=q else 0;trials=20000;passed=sum(all(i<k for i in rng.sample(range(n),q)) for _ in range(trials))
  bounds.append({'N':n,'q':q,'requested_fraction':f,'k':k,'record_fraction':k/n,'theoretical_pass':p,'uniform_sample_simulation_trials':trials,'passes':passed,'simulated_pass':passed/trials,'wilson95':rate_interval(passed,trials)})
cache_model=[]
for n,q in [(16,4),(64,8),(256,8)]:
 ratios=[]
 for k in range(q,n+1):
  p=math.comb(k,q)/math.comb(n,q);any_pass=1-(1-p)**3
  ratios.append((k/n/any_pass,k,p,any_pass))
 best=min(ratios);cache_model.append({'N':n,'q':q,'challenges':3,'best_fraction':best[1]/n,'best_correct_records':best[1],'single_pass':best[2],'any_pass':best[3],'historical_work_per_expected_credit_relative_to_full':best[0]})
oldplan=json.loads(Path('docs/evaluation/docking_whole_runs_2026-09-08/plan.json').read_text());assets=[]
for p in [Path(m['path']) for m in oldplan['maps']]+[Path('tmp/docking-runs/whole_run.wasm'),Path('tmp/docking-runs/whole_run_type_cache.wasm')]:
 if p.exists():
  b=p.read_bytes();assets.append({'path':p.as_posix(),'bytes':len(b),'gzip_bytes':len(gzip.compress(b,mtime=0)),'sha256':hashlib.sha256(b).hexdigest()})
out={'scope':'Observed complete local runs, historical runtime model simulations and analytic bounds kept separate. Server full ratios include measured local IPC and SQLite transactions where available; internet RTT/mobile/network throughput not measured. Memory is WASM heap capacity, not full browser RSS. Risk timing includes its SQL, so no unsupported pure CPU/DB split.','live':live,'shared_type_cache':cached,'policy_simulations':simulations,'audit_bounds':bounds,'fixed_cache_model':{'scope':'Analytic favorable-to-attacker fixed homogeneous tier/cache, three independent challenges, one possible credit. Ignores new-tier cost and cooldown. Not an implemented adaptive attack or cryptographic lower bound. Small savings can remain even with finite retries.','rows':cache_model},'cold_assets':assets}
(OUT/'economics_summary.json').write_text(json.dumps(out,indent=2)+'\n');print('Wrote economics_summary.json')
