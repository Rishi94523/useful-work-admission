"""Restore published public transcripts, refusing to replace different local runs."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
for record in json.loads((OUT/'transcripts.json').read_text()):
    if Path(record['file']).name!=record['file'] or Path(record['raw_file']).name!=record['raw_file']:raise ValueError('Invalid artifact path')
    blob=(OUT/record['file']).read_bytes();assert hashlib.sha256(blob).hexdigest()==record['gzip_sha256'];raw=gzip.decompress(blob);assert hashlib.sha256(raw).hexdigest()==record['raw_sha256'];target=OUT/record['raw_file']
    if target.exists() and target.read_bytes()!=raw:raise ValueError('Different local results: '+str(target))
    if not target.exists():target.write_bytes(raw)
    print('Verified',target.name)
