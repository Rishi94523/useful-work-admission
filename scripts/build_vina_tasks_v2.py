"""Build the v2 scientific driver: rescore every submitted minimum before merging.

The v1 driver finalizes a campaign by reading each client's minima pool with
task_read and merging on the energies the client reported. Phase 6 showed that
fabricated minima claiming very low energies evict honest ones from the bounded
merged set before refinement, hiding the best pose. v2 recomputes each read
minimum's energy and heavy-atom coordinates from its conformation, exactly as
the Monte Carlo search computed them when it saved the minimum (model::set then
eval_deriv at authentic_v), so client-reported energies and coordinates never
influence selection. An honest pool therefore finalizes identically to v1.

v1 is left untouched as the historical experimental baseline. v2 starts from
v1's patched sources, applies only this change to parallel_mc.cpp, and builds
into separate directories and executables.
"""
import hashlib,json,shutil,subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
V1_SRC=ROOT/'tmp/vina-tasks/source'
SRC=ROOT/'tmp/vina-tasks-v2/source'
BUILD=ROOT/'tmp/vina-tasks-v2/build'
BOOST=ROOT/'tmp/docking-pilot/boost/ucrt64'
DRIVER=ROOT/'research/native/vina_published_worker.cpp'
MAIN=ROOT/'tmp/docking-pilot/native/main.cpp'
GLOBALS=ROOT/'research/native/vina_reference_globals.cpp'
D_EXE=ROOT/'tmp/vina-published/vina_published_tasks_v2.exe'
R2_EXE=ROOT/'tmp/vina-reference/vina_ref_instrumented_v2.exe'
FLAGS=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off']
ANCHOR='   if(split_mode==2){task_read(path,task.out,m.get_size(),m.get_heavy_atom_movable_coords().size(),mc.num_saved_mins);continue;}'
PATCH='''   if(split_mode==2){
    task_read(path,task.out,m.get_size(),m.get_heavy_atom_movable_coords().size(),mc.num_saved_mins);
    // v2: never trust client-reported energies or coordinates. Recompute both
    // from the conformation, as monte_carlo did when saving the minimum.
    model rescore=m;const vec authentic(1000,1000,1000);change g(m.get_size());
    for(auto& o:task.out){rescore.set(o.c);o.e=rescore.eval_deriv(p,ig,authentic,g);o.coords=rescore.get_heavy_atom_movable_coords();}
    continue;}'''

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(args):
 r=subprocess.run([str(a) for a in args],capture_output=True,text=True)
 if r.returncode:raise RuntimeError(' '.join(map(str,args))[:300]+'\n'+r.stderr[-6000:])

def main():
 compiler=shutil.which('g++');assert compiler
 shutil.rmtree(SRC,ignore_errors=True);shutil.copytree(V1_SRC,SRC);BUILD.mkdir(parents=True,exist_ok=True)
 pmc=SRC/'parallel_mc.cpp';s=pmc.read_text()
 assert s.count(ANCHOR)==1,'v1 merge anchor not found exactly once'
 pmc.write_text(s.replace(ANCHOR,PATCH))
 inc=['-I'+str(SRC),'-I'+str(BOOST/'include')]
 sources=[p for p in SRC.glob('*.cpp') if p.stem!='parallel_progress']
 def compile(p):
  obj=BUILD/(p.stem+'.o');run(['g++',*FLAGS,*inc,'-c',p,'-o',obj]);return obj
 with ThreadPoolExecutor(max_workers=6) as pool:objects=sorted(pool.map(compile,sources))
 drv=BUILD/'vina_published_worker.o';run(['g++',*FLAGS,*inc,'-c',DRIVER,'-o',drv])
 run(['g++',*FLAGS,drv,*objects,'-static-libgcc','-static-libstdc++','-o',D_EXE])
 lib=[BOOST/'lib'/n for n in ('libboost_program_options-mt.a','libboost_filesystem-mt.a')]
 mo=BUILD/'main_instrumented.o';run(['g++',*FLAGS,'-DVERSION="v1.2.7"',*inc,'-c',MAIN,'-o',mo])
 go=BUILD/'globals.o';run(['g++',*FLAGS,*inc,'-c',GLOBALS,'-o',go])
 run(['g++',*FLAGS,mo,go,*objects,*lib,'-static-libgcc','-static-libstdc++','-static','-o',R2_EXE])
 manifest={'version':'v2-rescore-before-merge','compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],'flags':FLAGS,
  'derived_from_v1_source':{p.name:digest(p) for p in sorted(V1_SRC.iterdir()) if p.is_file()},
  'v2_source':{p.name:digest(p) for p in sorted(SRC.iterdir()) if p.is_file()},'patch':PATCH,
  'driver_exe_sha256':digest(D_EXE),'reference_instrumented_exe_sha256':digest(R2_EXE),
  'v1_driver_exe_sha256_unchanged':digest(ROOT/'tmp/vina-published/vina_published_tasks_spacing0375.exe')}
 (ROOT/'tmp/vina-tasks-v2/build_manifest.json').write_text(json.dumps(manifest,indent=2))
 changed=[n for n in manifest['v2_source'] if manifest['v2_source'][n]!=manifest['derived_from_v1_source'].get(n)]
 print('built',D_EXE.name,R2_EXE.name,'| source files changed from v1:',changed)

if __name__=='__main__':main()
