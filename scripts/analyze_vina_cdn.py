"""Pull optional remote reports and independently verify scientific signatures."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--pull',action='store_true');args=p.parse_args()
out=Path('docs/evaluation/vina_cdn_2026-09-14');manifest=json.loads((out/'manifest.json').read_text());expected=manifest['expected']
confirmation_path=out/'phone_session_confirmation.json'
confirmation=json.loads(confirmation_path.read_text()) if confirmation_path.exists() else {}
if args.pull:
 def kv(*parts):
  r=subprocess.run(['wrangler.cmd','kv','key',*parts,'--binding','RESULTS','--remote','--config','cloudflare/vina-cdn/wrangler.json'],capture_output=True,text=True,check=True)
  return json.loads(r.stdout)
 for item in kv('list','--prefix','device_'):
  path=out/(item['name']+'.json')
  if not path.exists():path.write_text(json.dumps(kv('get',item['name'],'--text'),indent=2)+'\n')
rows=[];seen=set()
for path in sorted([*out.glob('device_*.json'),*out.glob('desktop_*.json')]):
 r=json.loads(path.read_text())
 if r['id'] in seen:continue
 seen.add(r['id']);runs=[]
 for x in r['runs']:
  z={k:v for k,v in x.items() if k not in ['pool','trace','resources']};e=expected['tasks'][x['index']]
  z['exact']=all(hashlib.sha256(x[k].encode()).hexdigest()==e[k] for k in ['pool','trace'])
  z['resources']=[a for a in x.get('resources',[]) if '/delivery/' in a['name']]
  runs.append(z)
 row={k:r.get(k) for k in ['id','device_model','low_power_mode_reported','variant','cold_state_user_reported','prior_visit_marker','visits','hidden_events','error']}
 row['browser_cache_empty_confirmed_in_followup']=r['id'] in confirmation.get('applies_to',[]) and confirmation.get('browser_cache_empty_user_confirmed',False)
 row.update(source=path.name,runs=runs,complete=len(runs)==4 and {x['index'] for x in runs}==set(range(4)) and not r.get('error') and not r.get('stopped'),final_exact=r.get('finalization',{}).get('final_pose_sha256')==expected['final_pose_sha256'],artifact_exact=r.get('artifact_sha256')==manifest['artifact_sha256'],wasm_exact=r.get('wasm_sha256')==manifest['wasm_sha256'])
 rows.append(row);print(path.name,r.get('device_model'),r.get('variant'),[(x['mode'],round(x['end_to_end_ms']),x['exact']) for x in runs],row['final_exact'])
(out/'summary.json').write_text(json.dumps({'rows':rows,'scope':'Cold browser state is user-reported on iPhone and new isolated contexts on desktop; no query cache busting. Contribution timer excludes user dwell and initial document navigation, which is recorded separately. CDN edge state is independent of browser coldness. Client finalization digest is checked against the precomputed reference; not an admission security proof.'},indent=2)+'\n')
