"""Expose original MC task boundaries; preserve seed stream, pool and finalizer."""
from pathlib import Path
import hashlib,json,shutil,subprocess
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/vina-tasks';SRC=BASE/'source';BUILD=BASE/'build';OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10'
for p in [SRC,BUILD,OUT]:p.mkdir(parents=True,exist_ok=True)
def replace(s,a,b):
 assert a in s,a[:100]
 return s.replace(a,b)
patches=[]
for p in (ROOT/'tmp/docking-pilot/source/src/lib').iterdir():
 if not p.is_file():continue
 s=p.read_text();original=s
 s=s.replace('#include <boost/filesystem/fstream.hpp>','#include <fstream>\n#include <filesystem>').replace('#include <boost/filesystem.hpp>','#include <filesystem>').replace('#include <boost/filesystem/path.hpp>','#include <filesystem>').replace('boost::filesystem::ifstream','std::ifstream').replace('boost::filesystem::ofstream','std::ofstream').replace('boost::filesystem','std::filesystem')
 if p.name=='vina.h':
  for h in ['boost/log/core.hpp','boost/log/trivial.hpp','boost/log/expressions.hpp','boost/program_options.hpp','boost/thread/thread.hpp']:s=s.replace('#include <'+h+'>','')
  s=s.replace('boost::thread::hardware_concurrency()','1')
  s=replace(s,'\tvoid cite();','\tmodel initial_model;\n\tvoid save_initial(){initial_model=m_model;}\n\tvoid restore_initial(int seed){m_seed=seed;m_model=initial_model;m_poses=output_container();}\n\tvoid cite();')
 if p.name=='vina.cpp':
  s='#include "vina_task_io.h"\n'+s
  s=replace(s,'\t// Docking post-processing and rescoring','\tif(split_mode==1)return;\n\t// Docking post-processing and rescoring')
 if p.name=='monte_carlo.cpp':
  s='#include "vina_task_io.h"\n'+s
  s=replace(s,'\t\toutput_type candidate = tmp;','\t\t++split_steps;\n\t\toutput_type candidate = tmp;')
  s=replace(s,'\t\tif(step == 0 || metropolis_accept','\t\tsplit_trace.push_back(candidate.e);split_trace.push_back(evalcount);\n\t\tif(step == 0 || metropolis_accept')
  s=replace(s,'\tVINA_CHECK(!out.empty());','\tsplit_evals += evalcount;\n\tVINA_CHECK(!out.empty());')
 if p.name=='parallel_mc.cpp':
  s='#include "vina_task_io.h"\n'+s
  s=s.replace('#include "parallel.h"','').replace('#include "parallel_progress.h"','').replace('parallel_progress*','incrementable*')
  s=s.replace('\tparallel_progress pp (progress_callback);','').replace('(display_progress ? (&pp) : NULL)','NULL')
  start=s.index('\tif(display_progress) \n');end=s.index('\tmerge_output_containers(task_container',start)
  s=s[:start]+'''\tfor(sz i=0;i<task_container.size();i++){
   auto& task=task_container[i];const std::string path=split_folder+"/"+std::to_string(i)+".task";
   if(split_mode==2){task_read(path,task.out,m.get_size(),m.get_heavy_atom_movable_coords().size(),mc.num_saved_mins);continue;}
   if(split_mode==1 && int(i)!=split_index)continue;
   split_evals=0;split_steps=0;split_trace.clear();auto started=std::chrono::steady_clock::now();parallel_mc_aux_instance(task);
   double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-started).count();
   task_write(path,task.out);
   std::ofstream trace(path+".trace");trace<<std::setprecision(17);for(auto x:split_trace)trace<<x<<'\\n';trace.close();
   std::ofstream metrics(path+".json");metrics<<std::setprecision(17)<<"{\\"ms\\":"<<ms<<",\\"evals\\":"<<split_evals<<",\\"steps\\":"<<split_steps<<",\\"minima\\":"<<task.out.size()<<"}";
  }
  if(split_mode==1)return;
''' +s[end:]
 (SRC/p.name).write_text(s)
 if s!=original:patches.append({'file':p.name,'original':hashlib.sha256(p.read_bytes()).hexdigest(),'patched':hashlib.sha256(s.encode()).hexdigest()})
shutil.copyfile(ROOT/'research/native/vina_task_io.h',SRC/'vina_task_io.h')
compiler=shutil.which('g++');flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-I'+str(SRC),'-I'+str(ROOT/'tmp/docking-pilot/boost/ucrt64/include')]
sources=[p for p in SRC.glob('*.cpp') if p.stem!='parallel_progress']+[ROOT/'research/native/vina_task_worker.cpp']
def compile(p):
 obj=BUILD/(p.stem+'.o');signature=hashlib.sha256(p.read_bytes()+json.dumps(patches).encode()+(SRC/'vina_task_io.h').read_bytes()).hexdigest();stamp=obj.with_suffix('.sig')
 if not obj.exists() or not stamp.exists() or stamp.read_text()!=signature:
  r=subprocess.run([compiler,*flags,'-c',str(p),'-o',str(obj)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr[-6000:])
  stamp.write_text(signature)
 return obj
with ThreadPoolExecutor(max_workers=3) as pool:objects=list(pool.map(compile,sources))
exe=BASE/'vina_tasks.exe';subprocess.run([compiler,*flags,*map(str,objects),'-static-libgcc','-static-libstdc++','-o',str(exe)],check=True)
(OUT/'build.json').write_text(json.dumps({'patches':patches,'flags':flags,'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'scope':'Native single-thread task-boundary prototype. Original MC arithmetic, RNG allocation, n_poses pool and explicit receptor finalization; no shared-table optimization.'},indent=2)+'\n')
print(exe)
