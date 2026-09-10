"""Compact raw process samples and cross-check all recorded equivalence claims."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_resources_2026-09-10'
summary=[];eq=json.loads((OUT/'equivalence.json').read_text())
for t in ['fa10','hs90a','tryb1']:
 baseline=json.loads((OUT/f'baseline_{t}.json').read_text())
 for variant in ['baseline','moves','compact','compact_single']:
  path=OUT/f'{variant}_{t}.json'
  if not path.exists():continue
  r=json.loads(path.read_text());memory=json.loads(path.with_name(path.stem+'_working_set.json').read_text());assert not memory['errors']
  exact=all(a['pool_sha256']==b['pool_sha256'] and a['trace_sha256']==b['trace_sha256'] for a,b in zip(r['runs'],baseline['runs']))
  assert len(r['runs'])==len(baseline['runs']) and exact
  node=next((v for e in eq['results'] if e['target']==t for v in e['byVariant'] if v['variant']==variant),None)
  cross_runtime=all(node['tasks'][i]['pool']==r['runs'][i]['pool_sha256'] and node['tasks'][i]['trace']==r['runs'][i]['trace_sha256'] for i in [0,1]) if node else None
  if node:assert cross_runtime
  summary.append({'target':t,'variant':variant,'init_ms':r['init']['init_ms'],'module_ms':r['init']['module_ms'],'init_heap_bytes':r['init']['profile'][-1]['heap_bytes'],'init_live_bytes':r['init']['profile'][-1]['live_bytes'],'observed_allocator_live_peak_bytes':max(x['live_bytes'] for x in r['init']['profile']),'max_postrun_heap_bytes':max(x['profile'][-1]['heap_bytes'] for x in r['runs']),'renderer_os_peak_working_set_bytes':max(x['os_peak_working_set'] for x in memory['peaks'].values() if x['type']=='renderer'),'renderer_os_peak_commit_bytes':max(x['os_peak_commit'] for x in memory['peaks'].values() if x['type']=='renderer'),'exact_against_baseline':exact,'chrome_node_first_two_exact':cross_runtime,'measurement_wasm_sha256':r['wasm_sha256']})
archives=[]
for p in OUT.glob('*_working_set.json'):
 data=p.read_bytes();dest=p.with_suffix('.json.gz');dest.write_bytes(gzip.compress(data,mtime=0));assert gzip.decompress(dest.read_bytes())==data
 archives.append({'file':dest.name,'uncompressed_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(OUT/'summary.json').write_text(json.dumps({'scope':'Individual measured runs, not confidence intervals. OS peak working set includes renderer overhead. Earlier profiling builds precede added finalizer export; each measurement carries its own WASM hash. The final equivalence experiment separately records the final build hashes.','rows':summary,'archives':archives},indent=2)+'\n')
print('packaged',len(summary),'measurements;',len(archives),'process archives')
