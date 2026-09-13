"""Separate measured cold, HTTP cache miss, explicit cache hit and worker reuse."""
import json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_prepared_2026-09-13'
eq=json.loads((OUT/'equivalence.json').read_text());fa=next(r for r in eq['rows'] if r['target']=='fa10');expected=next(m for m in fa['modes'] if m['mode']=='reference')['tasks'];build=json.loads((OUT/'build.json').read_text())
rows=[]
for path in sorted(OUT.glob('device_[0-9]*.json')):
 r=json.loads(path.read_text());runs=[]
 for run in r['runs']:
  x={k:v for k,v in run.items() if k not in ['pool','trace','resources']};e=expected[run['index']]
  x['exact']=all(hashlib.sha256(run[k].encode()).hexdigest()==e[k] for k in ['pool','trace'])
  resource=next((p for p in run.get('resources',[]) if p['name'].endswith('/prepared.bin')),None)
  x['artifact_transfer_bytes']=resource['transferSize'] if resource else None
  x['http_artifact_cache_hit']=resource is not None and resource['transferSize']==0 and resource['decodedBodySize']>0
  x['indexeddb_hit']=run.get('artifact_cache_source')=='indexeddb'
  x['heap_mib']=run['heap']/2**20;runs.append(x)
 rows.append(dict(source=path.name,device=r['device_model'],cache_policy=r.get('cache_policy','http-only-v1'),
  low_power_mode_reported=r.get('low_power_mode_reported'),hidden_events=r['hidden_events'],
  complete=len(runs)==4 and sorted(x['index'] for x in runs)==list(range(4)) and not r.get('error') and not r.get('stopped'),
  artifact_hash_matches=r['artifact_sha256']==fa['artifact']['sha256'],wasm_hash_matches=r['wasm_sha256']==build['wasm_sha256'],runs=runs,error=r.get('error')))
summary=dict(artifacts=[dict(target=r['target'],**r['artifact']) for r in eq['rows']],devices=rows,
 scope='Browser timing is first-result wall time including download/decode, integrity checking, factory, input copying, restore/compute and one actual256k unit. Cold forces WASM/input/artifact reload; JS module cache is not explicitly cleared. Ordered single-trial modes use different seed indices; not device-population statistics. Localhost secure context uses WebCrypto; LAN HTTP uses tested JS SHA fallback. Browser transfer timing absence is not automatically a cache hit. IndexedDB hits are explicitly recorded. True WAN cold performance and physical phone results depend on received reports.')
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for r in rows:print(r['device'],[(x['mode'],round(x['end_to_end_ms']),x['exact'],x['indexeddb_hit']) for x in r['runs']])
