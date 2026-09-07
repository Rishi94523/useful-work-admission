"""Compile a persistent Vina wrapper using workspace-only downloaded dependencies."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'tmp/docking-pilot'
UPSTREAM=CACHE/'source/src/lib'
SRC=CACHE/'cached-source'
BOOST=CACHE/'boost/ucrt64'
BUILD=CACHE/'build'

def main():
    BUILD.mkdir(exist_ok=True)
    SRC.mkdir(exist_ok=True)
    for source in UPSTREAM.iterdir():
        if source.is_file():
            payload=source.read_bytes()
            if source.name=='vina.h':
                payload=payload.replace(b'\tvoid cite();',b'\tvoid set_ligand_pose_cached(const std::string& text);\n\tvoid cite();')
            dest=SRC/source.name
            if not dest.exists() or dest.read_bytes()!=payload:dest.write_bytes(payload)
    compiler=shutil.which('g++')
    if not compiler: raise RuntimeError('A C++ compiler is required')
    flags=['-O3','-std=c++17','-DNDEBUG','-DBOOST_ALL_NO_LIB','-D_WIN32_WINNT=0x0A00','-DBOOST_USE_WINAPI_VERSION=0x0A00','-I'+str(SRC),'-I'+str(BOOST/'include')]
    sources=list(SRC.glob('*.cpp'))+[ROOT/'research/native/vina_pose_cache.cpp',ROOT/'research/native/docking_worker.cpp']
    objects=[]
    def compile_one(source):
        obj=BUILD/(source.stem+'.o')
        signature=hashlib.sha256((json.dumps(flags)+hashlib.sha256(source.read_bytes()).hexdigest()).encode()).hexdigest()
        stamp=obj.with_suffix('.signature')
        if not obj.exists() or not stamp.exists() or stamp.read_text()!=signature:
            result=subprocess.run([compiler,*flags,'-c',str(source),'-o',str(obj)],capture_output=True,text=True)
            if result.returncode:
                raise RuntimeError(source.name+'\n'+result.stderr[-16000:])
            stamp.write_text(signature)
        print(source.name,flush=True)
        return obj
    with ThreadPoolExecutor(max_workers=3) as pool: objects=list(pool.map(compile_one,sources))
    libs=[]
    for name in ['thread','filesystem','chrono','atomic']:
        matches=[p for p in (BOOST/'lib').glob('libboost_'+name+'*.a') if not p.name.endswith('.dll.a')]
        if matches: libs.append(str(matches[0]))
    output=BUILD/'docking_worker.exe'
    command=[compiler,*map(str,objects),*libs,'-static-libgcc','-static-libstdc++','-lws2_32','-lbcrypt','-o',str(output)]
    result=subprocess.run(command,capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stderr[-20000:])
    record={'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],'flags':flags,'libraries':libs,'wrapper_sha256':hashlib.sha256(sources[-1].read_bytes()).hexdigest(),'cache_extension_sha256':hashlib.sha256(sources[-2].read_bytes()).hexdigest(),'patched_header_sha256':hashlib.sha256((SRC/'vina.h').read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'scope':'Pinned Vina 1.2.7 scoring/search formulas plus a guarded same-ligand pair-table cache and timing/IPC wrapper. Original downloaded source preserved separately.'}
    (ROOT/'docs/evaluation/docking_pilot_2026-09-06/native_build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print('Built',output,flush=True)

if __name__=='__main__':main()
