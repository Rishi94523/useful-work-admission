"""Download the maintainer's public phase-one artifact and record/check its hash."""
from pathlib import Path
import hashlib
import json
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'tmp/docking-ladder'
OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'
URL='https://pse-trusted-setup-ppot.s3.eu-central-1.amazonaws.com/pot28_0080/ppot_0080_19.ptau'

def main():
    BASE.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    dest=BASE/'ppot_0080_19.ptau'
    manifest=OUT/'setup_download.json'
    expected=json.loads(manifest.read_text()).get('blake2b') if manifest.exists() else None
    start=time.perf_counter()
    if not dest.exists():
        partial=dest.with_suffix('.download')
        count=0
        with urllib.request.urlopen(URL,timeout=120) as response,partial.open('wb') as output:
            while chunk:=response.read(4*1024*1024):
                count+=len(chunk)
                if count>700_000_000:raise ValueError('Download cap exceeded')
                output.write(chunk)
                if count%(64*1024*1024)==0:print('Downloaded MiB',count//1048576,flush=True)
        with partial.open('rb') as stream:digest=hashlib.file_digest(stream,'blake2b').hexdigest()
        if expected and digest!=expected:raise ValueError('Public setup checksum differs from recorded run')
        partial.replace(dest)
    with dest.open('rb') as stream:digest=hashlib.file_digest(stream,'blake2b').hexdigest()
    if expected and digest!=expected:raise ValueError('Cached setup checksum mismatch')
    record={'url':URL,'bytes':dest.stat().st_size,'blake2b':digest,'source':'https://github.com/privacy-ethereum/perpetualpowersoftau#prepared-and-truncated-files','power':19,'wall_seconds':time.perf_counter()-start,'scope':'Canonical maintainer download over HTTPS; local fingerprint recorded, not independently authenticated against a published digest or ceremony audit. Each final circuit key receives a local development phase-two contribution. Not production keys. Older Hermez Google/S3 URLs returned HTTP 403.'}
    manifest.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)

if __name__=='__main__':main()
