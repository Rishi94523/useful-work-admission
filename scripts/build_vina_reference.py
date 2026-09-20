"""Build the two same-toolchain Vina reference CLIs for the build-equivalence gate.

R1 stock: unpatched upstream library sources plus the official command-line main.
R2 instrumented: the split-task library objects already used by the distributed
harness, plus the same official main and a translation unit supplying the split
globals. Both use this machine's g++ and identical optimisation/FP flags, so a
difference between them isolates the instrumentation rather than the toolchain.

R1 additionally defines the Windows API version, because unpatched vina.h pulls
in boost/thread and this Boost build declares its atomic wait operations only at
Windows 8 and above. The patched library removes that include, so R2 does not
need the define. This asymmetry is recorded in the manifest rather than hidden.
"""
import hashlib,json,os,shutil,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STOCK_SRC=ROOT/'tmp/docking-pilot/source/src/lib'
PATCHED_OBJ=ROOT/'tmp/vina-tasks/build'
MAIN=ROOT/'tmp/docking-pilot/native/main.cpp'
GLOBALS=ROOT/'research/native/vina_reference_globals.cpp'
BOOST=ROOT/'tmp/docking-pilot/boost/ucrt64'
OUT=ROOT/'tmp/vina-reference'
BUILD=OUT/'build-stock'
FLAGS=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off']
STOCK_ONLY=['-D_WIN32_WINNT=0x0A00','-DBOOST_USE_WINAPI_VERSION=0x0A00']
VERSION=['-DVERSION="v1.2.7"']

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));os.replace(tmp,p)
def freeze(p,x):
 if p.exists():assert json.loads(p.read_text())==x,'Immutable manifest changed: '+str(p)
 else:save(p,x)

def run(args):
 r=subprocess.run([str(a) for a in args],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(' '.join(map(str,args))+'\n'+r.stderr[-6000:])

def main():
 compiler=shutil.which('g++');assert compiler,'g++ not found'
 for p in (OUT,BUILD):p.mkdir(parents=True,exist_ok=True)
 # Static archive order is significant; keep dependants ahead of dependencies.
 lib=[BOOST/'lib'/name for name in ('libboost_program_options-mt.a','libboost_filesystem-mt.a')]
 thread_lib=[BOOST/'lib'/name for name in ('libboost_thread-mt.a','libboost_atomic-mt.a','libboost_chrono-mt.a')]
 inc=['-I'+str(BOOST/'include')]

 # R1: unpatched upstream library, official main.
 sources=sorted(STOCK_SRC.glob('*.cpp'))
 def compile_stock(p):
  obj=BUILD/(p.stem+'.o');run([compiler,*FLAGS,*STOCK_ONLY,'-I'+str(STOCK_SRC),*inc,'-c',p,'-o',obj]);return obj
 with ThreadPoolExecutor(max_workers=6) as pool:stock_objects=list(pool.map(compile_stock,sources))
 main_stock=OUT/'main_stock.o';run([compiler,*FLAGS,*STOCK_ONLY,*VERSION,'-I'+str(STOCK_SRC),*inc,'-c',MAIN,'-o',main_stock])
 r1=OUT/'vina_ref_stock.exe'
 run([compiler,*FLAGS,main_stock,*stock_objects,*lib,*thread_lib,'-static-libgcc','-static-libstdc++','-static','-o',r1])

 # R2: existing split-task objects, official main, split globals.
 patched_objects=sorted(p for p in PATCHED_OBJ.glob('*.o') if p.name!='vina_task_worker.o')
 patched_src=ROOT/'tmp/vina-tasks/source'
 main_patched=OUT/'main_patched.o';run([compiler,*FLAGS,*VERSION,'-I'+str(patched_src),*inc,'-c',MAIN,'-o',main_patched])
 globals_obj=OUT/'globals.o';run([compiler,*FLAGS,'-I'+str(patched_src),*inc,'-c',GLOBALS,'-o',globals_obj])
 r2=OUT/'vina_ref_instrumented.exe'
 run([compiler,*FLAGS,main_patched,globals_obj,*patched_objects,*lib,'-static-libgcc','-static-libstdc++','-static','-o',r2])

 freeze(OUT/'reference_build.json',{
  'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
  'flags':FLAGS,'stock_only_flags':STOCK_ONLY,
  'stock':{'main':digest(MAIN),'source':{p.name:digest(p) for p in sorted(STOCK_SRC.iterdir()) if p.is_file()},'exe_sha256':digest(r1)},
  'instrumented':{'main':digest(MAIN),'globals':digest(GLOBALS),'objects':{p.name:digest(p) for p in patched_objects},'exe_sha256':digest(r2)},
  'official':{'exe_sha256':digest(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe')},
  'scope':'Same-toolchain references for the build-equivalence gate. R1 carries boost/thread and two Windows API defines that the patched library does not require; recorded, not waived.'})
 print(r1);print(r2)

if __name__=='__main__':main()
