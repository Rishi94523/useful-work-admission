"""Independent real Chrome/Node tier economics with shared XS preparation tables."""
import hashlib,json,os,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.adaptive_admission import AdaptiveAdmission
OLD=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08';OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
plan=json.loads((OLD/'plan.json').read_text());engine=json.loads((OUT/'build_wasm_type_cache.json').read_text())['wasm_sha256'];receptor=hashlib.sha256(json.dumps(plan['maps'],sort_keys=True).encode()).hexdigest()
assert all(r['exact_score_pose_trace_match'] for r in json.loads((OUT/'engine_equivalence.json').read_text())['checks'])
env={**os.environ,'DOCKING_TYPE_CACHE':'1'}
def start(script):
 p=subprocess.Popen(['node',script],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);r=json.loads(p.stdout.readline())
 if 'error' in r:raise RuntimeError(r)
 return p,r
def call(p,req):
 p.stdin.write(json.dumps(req)+'\n');p.stdin.flush();r=json.loads(p.stdout.readline())
 if 'error' in r:raise RuntimeError(r)
 return r
client,ci=start('scripts/adaptive_browser_ipc.mjs');server,si=start('scripts/adaptive_molecular_ipc.mjs');rows=[]
try:
 for repetition in range(3):
  for tier,score in [('low',0),('medium',20),('high',40)]:
   with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
    c=AdaptiveAdmission(Path(d)/'tier.sqlite',clock=lambda:0);jobs,runs,cap,q=c.TIERS[tier]
    # Initial risk is a controlled experimental input; full-loop trajectories are
    # measured separately. Fresh ranges, rotating molecule order, real outcomes.
    ids=plan['browser_ligands'];ids=ids[repetition:]+ids[:repetition]
    for ident in ids[:jobs]:
     ligand=next(l for l in plan['ligands'] if l['id']==ident)
     c.register('science',engine,receptor,ident,ligand['input_sha256'],'maps30A',70000+repetition*1000+score*16,16,cap,16)
    c.risk_state('visitor')
    with c.transaction() as db:db.execute('UPDATE risk SET score=? WHERE identity=?',(score,'visitor'))
    t=time.perf_counter();lease=c.request('science','visitor');admission_ms=(time.perf_counter()-t)*1000;assert lease['tier']==tier
    units=c.units(lease);t=time.perf_counter();computed=call(client,{'mode':'compute','units':units,'binding':lease['binding'],'fraction':1,'reuse':False});client_ipc=(time.perf_counter()-t)*1000
    t=time.perf_counter();ch=c.commit(lease['lease'],'visitor',lease['binding'],computed['commitment']['root']);challenge_ms=(time.perf_counter()-t)*1000;draws=c.flat_draws(lease,ch)
    t=time.perf_counter();checked=call(server,{'mode':'audit','units':units,'binding':lease['binding'],'commitment':computed['commitment'],'draws':draws,'openings':[computed['records'][i] for i in draws]});server_ipc=(time.perf_counter()-t)*1000
    t=time.perf_counter();outcome=c.finish(lease['lease'],'visitor',lease['binding'],ch['id'],computed['commitment']['root'],checked['accepted'],{'scientific_status':'provisional'});finish_ms=(time.perf_counter()-t)*1000;assert checked['accepted']
    row={'repetition':repetition,'tier':tier,'decision':{k:v for k,v in lease.items() if k!='tasks'},'units':units,'client':{k:v for k,v in computed.items() if k not in ['records','commitment']},'server':checked,'outcome':outcome,'draws':draws,'admission_and_scheduler_ms':admission_ms,'challenge_db_ms':challenge_ms,'finish_db_ms':finish_ms,'client_ipc_wall_ms':client_ipc,'server_ipc_wall_ms':server_ipc}
    rows.append(row);print('type-cache',repetition,tier,round(computed['total_ms']),round(checked['total_ms']),flush=True)
    (OUT/'cached_tier_economics.json').write_text(json.dumps({'scope':'Real Chrome Web Worker + separate Node verifier + SQLite controller. Risk initialized per tier, not a second feedback-loop test. Optimized XS table sharing; canonical equivalence tested separately. Sequential runs, one desktop, three bundles/tier.','client_init':ci,'server_init':si,'rows':rows},indent=2)+'\n')
finally:
 for p in [client,server]:
  p.stdin.write('{"mode":"quit"}\n');p.stdin.close()
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=15)
