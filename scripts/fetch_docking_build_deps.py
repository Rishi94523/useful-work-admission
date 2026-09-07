"""Workspace-only native build dependencies; verifies the published Boost SHA256."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'tmp/docking-pilot'
COMMIT='3c65c0b3e6c2c1d183f6a175ecb65e3c5ba91645'
BOOST='https://mirror.msys2.org/mingw/ucrt64/mingw-w64-ucrt-x86_64-boost-1.92.0-3-any.pkg.tar.zst'
BOOST_SHA='7b4450fb8bd4677282e676e1c7b471618357a1a2bd2a94c2a78fd45c3a7fc234'

def fetch(job):
    dest,url=job
    if not dest.exists():
        with urllib.request.urlopen(url,timeout=90) as response: payload=response.read(30_000_001)
        if len(payload)>30_000_000: raise ValueError('File cap')
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(payload)
    payload=dest.read_bytes()
    return dict(path=str(dest.relative_to(ROOT)),url=url,sha256=hashlib.sha256(payload).hexdigest(),bytes=len(payload))

def main():
    with urllib.request.urlopen(f'https://api.github.com/repos/ccsb-scripps/AutoDock-Vina/git/trees/{COMMIT}?recursive=1',timeout=30) as response: tree=json.load(response)
    paths=[f['path'] for f in tree['tree'] if f['type']=='blob' and f['path'].startswith('src/lib/')]
    with ThreadPoolExecutor(max_workers=6) as pool:
        records=list(pool.map(fetch,[(CACHE/'source'/p,f'https://raw.githubusercontent.com/ccsb-scripps/AutoDock-Vina/{COMMIT}/{p}') for p in paths]))
    print('Vina source files',len(records),flush=True)
    record=fetch((CACHE/'boost.pkg.tar.zst',BOOST))
    assert record['sha256']==BOOST_SHA, 'Boost archive checksum mismatch'
    records.append(record)
    base=(CACHE/'boost').resolve()
    base.mkdir(exist_ok=True)
    with tarfile.open(CACHE/'boost.pkg.tar.zst','r:zst') as archive:
        for member in archive:
            if not member.isfile(): continue
            if not (member.name.startswith('ucrt64/include/boost/') or (member.name.startswith('ucrt64/lib/libboost_') and member.name.endswith('.a')) or member.name.endswith('LICENSE_1_0.txt')): continue
            dest=(base/member.name).resolve()
            if not dest.is_relative_to(base): raise ValueError('Unsafe archive path')
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(archive.extractfile(member).read())
    out=ROOT/'docs/evaluation/docking_pilot_2026-09-06/build_inputs.json'
    out.write_text(json.dumps({'vina_commit':COMMIT,'boost_sha256_source':'https://packages.msys2.org/packages/mingw-w64-ucrt-x86_64-boost','files':records},indent=2)+'\n',encoding='utf-8')
    print('Extracted Boost headers and static libraries into',base,flush=True)

if __name__=='__main__':main()
