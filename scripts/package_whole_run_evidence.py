"""Compress public experimental transcripts; leave temporary toolchains unpublished."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
manifest=[]
for name in ['native.json','browser.json','wasm_science.json','wasm_control.json']:
    p=OUT/name;raw=p.read_bytes();blob=gzip.compress(raw,compresslevel=9,mtime=0);dest=p.with_suffix('.json.gz');dest.write_bytes(blob)
    manifest.append({'file':dest.name,'raw_file':name,'raw_sha256':hashlib.sha256(raw).hexdigest(),'gzip_sha256':hashlib.sha256(blob).hexdigest(),'raw_bytes':len(raw),'gzip_bytes':len(blob)})
(OUT/'transcripts.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
