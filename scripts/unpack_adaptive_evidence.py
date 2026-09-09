"""Verify published hashes; restore only contained paths and never overwrite edits."""
import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
def sha(b):return hashlib.sha256(b).hexdigest()
def write(path,data):
 if path.exists():
  if path.read_bytes()!=data:raise ValueError('Refusing to replace different existing file: '+str(path))
 else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
for a in json.loads((OUT/'transcripts.json').read_text())['archives']:
 if Path(a['name']).name!=a['name'] or Path(a['uncompressed_name']).name!=a['uncompressed_name']:raise ValueError('Invalid archive name')
 raw=(OUT/a['name']).read_bytes();assert sha(raw)==a['gzip_sha256'];data=gzip.decompress(raw);assert sha(data)==a['raw_sha256']
 if a['uncompressed_name']=='prepared_inputs.json':
  for name,r in json.loads(data)['files'].items():
   path=(ROOT/name).resolve()
   if not path.is_relative_to((ROOT/'tmp/adaptive-docking').resolve()):raise ValueError('Prepared input outside research cache')
   b=r['text'].encode();assert sha(b)==r['sha256'];write(path,b)
 else:write(OUT/a['uncompressed_name'],data)
print('Adaptive archives verified and restored')
