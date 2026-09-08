"""Actual WASM compute/replay linked to disjoint SQLite work-credit lifecycle."""
import hashlib,json,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
from research.whole_run_campaign import WholeRunCampaign
plan=json.loads((OUT/'plan.json').read_text());engine=json.loads((OUT/'build_wasm.json').read_text())['wasm_sha256'];receptor=hashlib.sha256(json.dumps(plan['maps'],sort_keys=True).encode()).hexdigest()
p=subprocess.Popen(['node','scripts/whole_run_ipc.mjs'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def reply():
    line=p.stdout.readline()
    if not line:raise RuntimeError('WASM process stopped')
    r=json.loads(line)
    if 'error' in r:raise RuntimeError(r)
    return r
def call(r):p.stdin.write(json.dumps(r)+'\n');p.stdin.flush();return reply()
init=reply();evidence={'runtime_initialization':init,'bundles':[]}
try:
 with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
  c=WholeRunCampaign(Path(d)/'credits.sqlite')
  for l in plan['ligands'][:4]:c.register('fa10',engine,receptor,l['id'],l['input_sha256'],'fixed-maps30A',0,4,4000,4*l['heavy_atoms'])
  t=time.perf_counter();lease=c.lease('fa10','research-worker',jobs=4,ttl=600);leaseMs=(time.perf_counter()-t)*1000;units=c.units(lease)
  computed=call({'mode':'compute','units':units,'binding':lease['binding']});root=computed['commitment']['root']
  t=time.perf_counter();challenge=c.commit(lease['lease'],'research-worker',lease['binding'],root,samples=4);challengeMs=(time.perf_counter()-t)*1000
  checked=call({'mode':'audit','draws':c.flat_draws(lease,challenge)});assert checked['accepted']
  t=time.perf_counter();c.finish(lease['lease'],'research-worker',lease['binding'],challenge['id'],root,True,{'scientific_status':'provisional','credit_kind':'previously-uncompleted-work'});creditMs=(time.perf_counter()-t)*1000
  exhausted=False;replayed=False
  try:c.lease('fa10','another-worker',jobs=1)
  except LookupError:exhausted=True
  try:c.finish(lease['lease'],'research-worker',lease['binding'],challenge['id'],root,True,{})
  except ValueError:replayed=True
  assert exhausted and replayed;evidence['bundles'].append({'jobs':4,'runs_per_job':4,'lease_ms':leaseMs,'challenge_ms':challengeMs,'credit_ms':creditMs,'compute_ms':computed['compute_ms'],'audit':checked,'completed_pool_exhausted':exhausted,'duplicate_credit_rejected':replayed,'snapshot':c.snapshot()})
finally:p.stdin.write('{"mode":"quit"}\n');p.stdin.flush();p.stdin.close();p.wait(timeout=10)
(OUT/'integration.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))
