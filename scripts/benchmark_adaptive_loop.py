"""Actual risk -> leased science -> client WASM -> independent server replay loop."""
import hashlib,json,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.adaptive_admission import AdaptiveAdmission
OLD=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08';OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
plan=json.loads((OLD/'plan.json').read_text());engine=json.loads((OLD/'build_wasm.json').read_text())['wasm_sha256'];receptor=hashlib.sha256(json.dumps(plan['maps'],sort_keys=True).encode()).hexdigest()
calibrated='--legacy-calibration' not in sys.argv
if not calibrated:
    AdaptiveAdmission.TIERS={**AdaptiveAdmission.TIERS,'low':(1,16,16000,4)}
    AdaptiveAdmission.VERSION='adaptive-outer-v1'
filename='adaptive_loop_calibrated.json' if calibrated else 'adaptive_loop.json'
def start(browser=False):
    p=subprocess.Popen(['node','scripts/adaptive_browser_ipc.mjs' if browser else 'scripts/adaptive_molecular_ipc.mjs'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True);init=json.loads(p.stdout.readline())
    if 'error' in init:raise RuntimeError(init)
    return p,init
def call(p,req):
    p.stdin.write(json.dumps(req)+'\n');p.stdin.flush();line=p.stdout.readline()
    if not line:raise RuntimeError('Molecular worker stopped')
    r=json.loads(line)
    if 'error' in r:raise RuntimeError(r)
    return r
client,ci=start(browser=calibrated);server,si=start();output={'policy':AdaptiveAdmission.VERSION,'scope':'Actual Chrome module-worker client in calibrated v2 (Node client in legacy v1), separate Node/WASM server, SQLite risk/scheduler, real molecular outcomes. Logical request clock is controlled; high-rate valid cases model precomputed/accelerated submission timing, not actual serial wall throughput.','client_init':ci,'server_init':si,'scenarios':[]}
try:
 for scenario,fraction,steps,reuse in [('honest',1,3,False),('valid-spam',1,20,False),('partial10',.1,5,False),('partial25',.25,5,False),('partial50',.5,5,False),('partial75',.75,5,False),('partial90',.9,5,False),('retry-cache',.5,5,True)]:
  now=[0];rows=[]
  with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
   c=AdaptiveAdmission(Path(d)/'loop.sqlite',clock=lambda:now[0])
   # Disjoint seed ranges between scenarios; repetitions are never double-credited.
   offset=(30000 if calibrated else 1000)+len(output['scenarios'])*1000
   for identifier in plan['browser_ligands']:
    ligand=next(l for l in plan['ligands'] if l['id']==identifier)
    for block in range(20):
     for cap,shift in ([(4000,0),(16000,400)] if calibrated else [(16000,0)]):
      c.register('science',engine,receptor,identifier,ligand['input_sha256'],'maps30A',offset+shift+block*16,16,cap,16*ligand['heavy_atoms'])
   for step in range(steps):
    t=time.perf_counter();lease=c.request('science','visitor');admission_ms=(time.perf_counter()-t)*1000
    row={'step':step,'decision':{k:v for k,v in lease.items() if k!='tasks'},'admission_and_scheduler_ms':admission_ms}
    if lease['status']!='assigned':rows.append(row);break
    units=c.units(lease);t=time.perf_counter();computed=call(client,{'mode':'compute','units':units,'binding':lease['binding'],'fraction':fraction,'reuse':reuse});client_ipc_ms=(time.perf_counter()-t)*1000
    t=time.perf_counter();ch=c.commit(lease['lease'],'visitor',lease['binding'],computed['commitment']['root']);challenge_ms=(time.perf_counter()-t)*1000;draws=c.flat_draws(lease,ch)
    t=time.perf_counter();checked=call(server,{'mode':'audit','units':units,'binding':lease['binding'],'commitment':computed['commitment'],'draws':draws,'openings':[computed['records'][i] for i in draws]});server_ipc_ms=(time.perf_counter()-t)*1000
    t=time.perf_counter();outcome=c.finish(lease['lease'],'visitor',lease['binding'],ch['id'],computed['commitment']['root'],checked['accepted'],{'scientific_status':'provisional'});finish_ms=(time.perf_counter()-t)*1000
    row.update(units=units,client={k:v for k,v in computed.items() if k not in ['records','commitment']},server=checked,outcome=outcome,challenge_db_ms=challenge_ms,finish_db_ms=finish_ms,draws=draws,client_ipc_wall_ms=client_ipc_ms,server_ipc_wall_ms=server_ipc_ms)
    rows.append(row);print(scenario,step,lease['tier'],checked['accepted'],round(computed['total_ms']),flush=True)
    now[0]+=60 if scenario=='honest' else .1
    (OUT/'adaptive_loop_progress.json').write_text(json.dumps({'completed':output,'active':rows},indent=2)+'\n')
   output['scenarios'].append({'name':scenario,'fraction':fraction,'rows':rows,'snapshot':c.snapshot()})
   (OUT/filename).write_text(json.dumps(output,indent=2)+'\n')
finally:
 for p in [client,server]:
  p.stdin.write('{"mode":"quit"}\n');p.stdin.close()
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=15)
