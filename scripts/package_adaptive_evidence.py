"""Archive complete scientific logs and small prepared public inputs, with hashes."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
inputs=json.loads((OUT/'science_inputs.json').read_text());converged=json.loads((OUT/'converged_inputs.json').read_text())['rows'];archives=[];prepared={}
def sha(b):return hashlib.sha256(b).hexdigest()
def archive(name,data):
 packed=gzip.compress(data,mtime=0);path=OUT/(name+'.gz');path.write_bytes(packed)
 archives.append({'name':path.name,'uncompressed_name':name,'raw_bytes':len(data),'gzip_bytes':len(packed),'raw_sha256':sha(data),'gzip_sha256':sha(packed)})
for t in inputs['targets']:
 if t.get('preparation_failed'):continue
 p=OUT/('science_'+t['target']+'.jsonl');rows=[json.loads(x) for x in p.read_text().splitlines()];latest={r['key']:r for r in rows}
 assert len(latest)==466,(t['target'],len(latest))
 assert all(r.get('cost_schema')==2 for r in latest.values() if r['method']=='local'),'Local cost remeasurement incomplete'
 archive(p.name,p.read_bytes())
 p=OUT/('low_science_'+t['target']+'.jsonl');assert len(p.read_text().splitlines())==288
 archive(p.name,p.read_bytes())
 for prefix,count in [('converged_redocking_',45),('converged_ranking_',592)]:
  p=OUT/(prefix+t['target']+'.jsonl');rows=[json.loads(x) for x in p.read_text().splitlines()]
  assert len(rows)==len({r['key'] for r in rows})==count,(p.name,len(rows))
  for r in rows:
   source=next(c for c in converged if c['target']==r['target'] and c['id']==r['id'])
   assert r['input_sha256']==source['sha256']
  archive(p.name,p.read_bytes())
 paths=[ROOT/t['receptor']]
 for l in t['ligands']:
  for c in ['source','independent']:
   p=ROOT/l[c]['path'];paths.extend([p,p.with_suffix('.sdf')])
 for c in [c for c in converged if c['target']==t['target']]:
  p=ROOT/c['path'];assert sha(p.read_bytes())==c['sha256'];paths.extend([p,p.with_suffix('.sdf')])
 for p in paths:
  b=p.read_bytes();prepared[p.relative_to(ROOT).as_posix()]={'sha256':sha(b),'text':b.decode()}
stock=OUT/'stock.jsonl';assert len(stock.read_text().splitlines())==54
archive(stock.name,stock.read_bytes())
for name,count in [('stock_converged_crystal.jsonl',3),('stock_converged_all.jsonl',51)]:
 p=OUT/name;rows=[json.loads(x) for x in p.read_text().splitlines()]
 assert len(rows)==len({r['key'] for r in rows})==count,(name,len(rows))
 archive(name,p.read_bytes())
archive('prepared_inputs.json',json.dumps({'scope':'Selected public DUD-E inputs prepared by the pinned pipeline. Original source URLs/hashes are in science_inputs.json. Receptor grids and toolchains excluded.','files':prepared},separators=(',',':')).encode())
(OUT/'transcripts.json').write_text(json.dumps({'archives':archives},indent=2)+'\n');print('Archived',len(archives),'complete artifacts')
