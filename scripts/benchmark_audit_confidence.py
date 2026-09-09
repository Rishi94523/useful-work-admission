"""Actual stronger-audit sweep on committed optimized browser bundles.

Diagnostic operating-point comparison, not multiple credits for the same work.
All audit samples are drawn after the client commitment. Each q has full replay.
"""
import json,os,secrets,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';OLD=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
plan=json.loads((OLD/'plan.json').read_text());env={**os.environ,'DOCKING_TYPE_CACHE':'1'}
engine_hash=json.loads((OUT/'build_wasm_type_cache.json').read_text())['wasm_sha256']
assert all(x['exact_score_pose_trace_match'] for x in json.loads((OUT/'engine_equivalence.json').read_text())['checks'])
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
 for rep in range(3):
  units=[]
  for ident in plan['browser_ligands']:
   ligand=next(l for l in plan['ligands'] if l['id']==ident)
   for i in range(16):units.append({'ligand':ident,'input':ligand['input_sha256'],'seed':104729+13007*(80000+rep*100+i),'cap':16000,'engine':engine_hash,'run':80000+rep*100+i})
  binding=secrets.token_hex(32);computed=call(client,{'mode':'compute','units':units,'binding':binding,'fraction':1,'reuse':False});audits=[]
  # Rotate q order to expose, rather than systematically hide, first-audit setup.
  qs=[8,16,27,40,57];qs=qs[rep:]+qs[:rep]
  for q in qs:
   draws=secrets.SystemRandom().sample(range(len(units)),q);t=time.perf_counter();checked=call(server,{'mode':'audit','units':units,'binding':binding,'commitment':computed['commitment'],'draws':draws,'openings':[computed['records'][i] for i in draws]});wall=(time.perf_counter()-t)*1000;assert checked['accepted']
   audits.append({'q':q,'draws':draws,'server':checked,'server_ipc_wall_ms':wall});print('audit-confidence',rep,q,round(wall),flush=True)
  rows.append({'repetition':rep,'units':units,'client':{k:v for k,v in computed.items() if k not in ['records','commitment']},'audits':audits})
  (OUT/'audit_confidence.json').write_text(json.dumps({'scope':'Actual committed 256-run Chrome bundles with independent complete-run Node audits at q8/16/27/40/57. Three bundles, rotating q order. No extra work credits, no stateful risk/DB stage in this diagnostic. Server IPC is local; cold init separate.','client_init':ci,'server_init':si,'rows':rows},indent=2)+'\n')
finally:
 for p in [client,server]:
  p.stdin.write('{"mode":"quit"}\n');p.stdin.close()
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:p.terminate();p.wait(timeout=15)
