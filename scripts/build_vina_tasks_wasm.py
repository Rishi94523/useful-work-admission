"""Compile the same instrumented task relation for Chrome/Node replay."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/vina-tasks';SRC=BASE/'source';BUILD=BASE/'wasm-build';BUILD.mkdir(exist_ok=True)
SDK=ROOT/'tmp/docking-runs/emsdk';env={**os.environ,'EM_CONFIG':str(SDK/'.emscripten'),'EM_CACHE':str(SDK/'upstream/emscripten/cache')};compiler=[sys.executable,str(SDK/'upstream/emscripten/em++.py')]
flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-fexceptions','-I'+str(SRC),'-I'+str(ROOT/'tmp/docking-pilot/boost/ucrt64/include')]
sources=[p for p in SRC.glob('*.cpp') if p.stem!='parallel_progress']+[ROOT/'research/native/vina_task_browser.cpp']
headers=b''.join(p.read_bytes() for p in sorted(SRC.glob('*.h')))
def compile(p):
 obj=BUILD/(p.stem+'.o');stamp=obj.with_suffix('.sig');signature=hashlib.sha256(p.read_bytes()+headers+json.dumps(flags).encode()).hexdigest()
 if not obj.exists() or not stamp.exists() or stamp.read_text()!=signature:
  r=subprocess.run([*compiler,*flags,'-c',str(p),'-o',str(obj)],env=env,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr[-6000:])
  stamp.write_text(signature)
 return obj
with ThreadPoolExecutor(max_workers=3) as pool:objects=list(pool.map(compile,sources))
target=BASE/'vina_tasks.mjs';link=['--no-entry','-fexceptions','-sDISABLE_EXCEPTION_CATCHING=0','-sMODULARIZE=1','-sEXPORT_ES6=1','-sENVIRONMENT=web,worker,node','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=1048576','-sEXPORTED_FUNCTIONS=["_vt_init","_vt_run","_vt_memory","_vt_seeds"]','-sEXPORTED_RUNTIME_METHODS=["ccall","FS"]']
subprocess.run([*compiler,*flags,*map(str,objects),*link,'-o',str(target)],env=env,check=True)
(ROOT/'docs/evaluation/vina_tasks_2026-09-10/build_wasm.json').write_text(json.dumps({'flags':flags,'link':link,'wasm_sha256':hashlib.sha256(target.with_suffix('.wasm').read_bytes()).hexdigest(),'worker_sha256':hashlib.sha256((ROOT/'research/native/vina_task_browser.cpp').read_bytes()).hexdigest(),'scope':'Same task source as native; numerical native/WASM equality is not assumed. Computes original maps from receptor; uncapped full MC units.'},indent=2)+'\n')
print(target)
