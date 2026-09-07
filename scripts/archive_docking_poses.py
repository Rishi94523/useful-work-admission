"""Export or restore the public pilot outputs, with hashes and constrained paths."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evaluation/docking_pilot_2026-09-06'
RUNS=(ROOT/'tmp/docking-pilot/runs').resolve()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--export',action='store_true')
    args=parser.parse_args()
    target=OUT/'pose_corpus.json'
    if args.export:
        paths=set()
        for name in ['native_scaling.json','browser_scaling.json','browser_full_search.json']:
            for row in json.loads((OUT/name).read_text())['rows']:
                if row.get('pose_path'):paths.add(row['pose_path'])
        records=[]
        for path in sorted(paths):
            payload=(ROOT/path).read_bytes()
            records.append({'path':path,'sha256':hashlib.sha256(payload).hexdigest(),'text':payload.decode('ascii')})
        target.write_text(json.dumps({'scope':'Generated poses from public Webina benchmark inputs; no novel binding or experimental efficacy claim. Raw serializations preserved for rescoring.','poses':records},indent=2)+'\n',encoding='utf-8')
    else:
        records=json.loads(target.read_text(encoding='utf-8'))['poses']
        # Validate every record before writing any file. Never overwrite different work.
        for row in records:
            path=(ROOT/row['path']).resolve()
            if path.parent!=RUNS or path.suffix!='.pdbqt':raise ValueError('Unexpected corpus path')
            payload=row['text'].encode('ascii')
            if hashlib.sha256(payload).hexdigest()!=row['sha256']:raise ValueError('Corpus hash mismatch')
            if path.exists() and path.read_bytes()!=payload:raise ValueError('Existing pose differs: '+str(path))
        RUNS.mkdir(parents=True,exist_ok=True)
        for row in records:(ROOT/row['path']).write_bytes(row['text'].encode('ascii'))
    print(len(records),'poses', 'exported' if args.export else 'restored/verified')

if __name__=='__main__':main()
