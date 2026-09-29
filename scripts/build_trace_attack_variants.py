"""Amendment 16: build the adaptive-attack driver variants.

Each variant starts from the frozen v1 driver sources (tmp/vina-tasks/source)
and is built exactly as scripts/build_vina_tasks_v2.py builds v2, changing only
the stated flags or one line. A control build with no change must reproduce
the honest driver before any variant is judged; its hash is compared with the
preserved honest driver.
"""
import hashlib,json,shutil,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
V1_SRC=ROOT/'tmp/vina-tasks/source'
BASE=ROOT/'tmp/trace-attacks'
BOOST=ROOT/'tmp/docking-pilot/boost/ucrt64'
DRIVER=ROOT/'research/native/vina_published_worker.cpp'
HONEST=ROOT/'tmp/vina-published/vina_published_tasks_spacing0375.exe'
FLAGS=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off']
FAST=['-O3','-std=c++17','-DNDEBUG','-ffast-math','-march=native']
LOCAL='quasi_newton_par.max_steps = local_steps;'
REFINE='quasi_newton_par(m, p, ig, tmp, g, authentic_v, evalcount);'
VARIANTS={
 'control':(FLAGS,None),
 'v1_fastmath':(FAST,None),
 'v2_halflocal':(FLAGS,(LOCAL,'quasi_newton_par.max_steps = (local_steps + 1) / 2; // amendment 16 V2')),
 'v3_norefine':(FLAGS,(REFINE,'/* amendment 16 V3: refinement skipped */')),
}

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args):
 r=subprocess.run([str(a) for a in args],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(' '.join(map(str,args))[:300]+'\n'+r.stderr[-6000:])

def build(name,flags,patch):
 src=BASE/name/'source';obj=BASE/name/'build';exe=BASE/name/'driver.exe'
 shutil.rmtree(BASE/name,ignore_errors=True);shutil.copytree(V1_SRC,src);obj.mkdir(parents=True)
 if patch:
  mc=src/'monte_carlo.cpp';s=mc.read_text();old,new=patch
  assert s.count(old)==1,(name,'anchor not found exactly once');mc.write_text(s.replace(old,new))
 inc=['-I'+str(src),'-I'+str(BOOST/'include')]
 sources=[p for p in src.glob('*.cpp') if p.stem!='parallel_progress']
 def compile(p):
  o=obj/(p.stem+'.o');run(['g++',*flags,*inc,'-c',p,'-o',o]);return o
 with ThreadPoolExecutor(max_workers=6) as pool:objects=sorted(pool.map(compile,sources))
 drv=obj/'vina_published_worker.o';run(['g++',*flags,*inc,'-c',DRIVER,'-o',drv])
 run(['g++',*flags,drv,*objects,'-static-libgcc','-static-libstdc++','-o',exe])
 return {'flags':flags,'patch':patch,'exe':str(exe.relative_to(ROOT)),'exe_sha256':digest(exe),
         'changed_sources':[p.name for p in sorted(src.iterdir()) if p.is_file() and digest(p)!=digest(V1_SRC/p.name)]}

def main():
 BASE.mkdir(parents=True,exist_ok=True)
 out={'compiler':subprocess.check_output(['g++','--version'],text=True).splitlines()[0],'honest_exe_sha256':digest(HONEST)}
 for name,(flags,patch) in VARIANTS.items():
  out[name]=build(name,flags,patch);print(name,out[name]['exe_sha256'][:16],out[name]['changed_sources'],flush=True)
 out['control_matches_honest_binary']=out['control']['exe_sha256']==out['honest_exe_sha256']
 (BASE/'build_manifest.json').write_text(json.dumps(out,indent=2));print('control binary identical to honest:',out['control_matches_honest_binary'])

if __name__=='__main__':main()
