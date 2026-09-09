"""Build a shared single-thread Vina relation for native and WASM.

Only orchestration/portability, explicit run seed, counters and reset API differ.
Upstream search, scoring, BFGS and termination rules remain intact.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'tmp/docking-runs';SRC=BASE/'source';OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
OLD=ROOT/'tmp/docking-pilot';BOOST=OLD/'boost/ucrt64/include';SDK=BASE/'emsdk'
def replace(text,a,b):
    if a not in text:raise ValueError('Patch anchor absent: '+a[:80])
    return text.replace(a,b)
def main():
    global SRC
    no_trace='--no-trace' in sys.argv
    adaptive='--adaptive' in sys.argv
    type_cache='--type-cache' in sys.argv
    if type_cache:adaptive=True
    if adaptive and (no_trace or '--native' in sys.argv):raise ValueError('Adaptive artifact is a separate traced WASM build')
    if adaptive:SRC=BASE/'source-adaptive'
    if type_cache:SRC=BASE/'source-type-cache'
    if no_trace:SRC=BASE/'source-no-trace'
    SRC.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    changes=[]
    for p in (OLD/'source/src/lib').iterdir():
        if not p.is_file():continue
        s=p.read_text();original=s
        s=s.replace('#include <boost/filesystem/fstream.hpp>','#include <fstream>\n#include <filesystem>').replace('#include <boost/filesystem.hpp>','#include <filesystem>').replace('#include <boost/filesystem/path.hpp>','#include <filesystem>')
        s=s.replace('boost::filesystem::ifstream','std::ifstream').replace('boost::filesystem::ofstream','std::ofstream').replace('boost::filesystem','std::filesystem')
        if p.name=='vina.h':
            for header in ['boost/log/core.hpp','boost/log/trivial.hpp','boost/log/expressions.hpp','boost/program_options.hpp']:
                s=s.replace('#include <'+header+'>','')
            s=s.replace('#include <boost/thread/thread.hpp>','// #include <boost/thread/thread.hpp>')
            s=s.replace('boost::thread::hardware_concurrency()','1')
            s=replace(s,'\tvoid cite();','\tmodel initial_model;\n\tvoid save_initial(){initial_model=m_model;}\n\tvoid restore_initial(int seed){m_seed=seed;m_model=initial_model;m_poses=output_container();}\n\tvoid cite();')
        if p.name=='parallel_mc.cpp':
            s=s.replace('#include "parallel.h"','').replace('#include "parallel_progress.h"','')
            s=s.replace('parallel_progress*','incrementable*')
            s=replace(s,'\tparallel_progress pp (progress_callback);','\textern int run_direct_seed;')
            s=s.replace('(display_progress ? (&pp) : NULL)','NULL')
            s=s.replace('random_int(0, 1000000, generator)','(run_direct_seed > 0 ? run_direct_seed : random_int(0, 1000000, generator))')
            begin=s.index('\tif(display_progress) \n');end=s.index('\tmerge_output_containers(task_container',begin)
            s=s[:begin]+'\tfor(auto& task:task_container) parallel_mc_aux_instance(task);\n'+s[end:]
        if p.name=='monte_carlo.cpp':
            s=replace(s,'    int evalcount = 0;','    extern int run_eval_count, run_mc_steps;\n    extern std::vector<double> run_trace;\n    int evalcount = 0;')
            s=replace(s,'\t\toutput_type candidate = tmp;','\t\t++run_mc_steps;\n\t\toutput_type candidate = tmp;')
            s=replace(s,'\tVINA_CHECK(!out.empty());','\trun_eval_count += evalcount;\n\tVINA_CHECK(!out.empty());')
            if not no_trace:s=replace(s,'\t\tif(step == 0 || metropolis_accept','\t\trun_trace.push_back(candidate.e);\n\t\trun_trace.push_back(evalcount);\n\t\tif(step == 0 || metropolis_accept')
        if type_cache and p.name=='scoring_function.h':
            s=replace(s,'        switch (sf_choice)','        m_choice=sf_choice;\n        switch (sf_choice)')
            s=replace(s,'    fl get_cutoff() const','    scoring_function_choice get_choice() const { return m_choice; }\n    fl get_cutoff() const')
            s=replace(s,'    flv m_weights;','    scoring_function_choice m_choice=SF_VINA;\n    flv m_weights;')
        if type_cache and p.name=='precalculate.h':
            begin=s.index('struct precalculate_byatom')
            s=s[:begin]+(ROOT/'research/native/shared_type_precalculate.h').read_text()+'\n#endif\n'
            s=s.replace('#include "matrix.h"','#include "matrix.h"\n#include <memory>\n#include <map>')
        dest=SRC/p.name;dest.write_text(s)
        if s!=original:changes.append({'file':p.name,'upstream_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'patched_sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
    native='--native' in sys.argv;build=BASE/('wasm-build-type-cache' if type_cache else 'wasm-build-adaptive' if adaptive else 'native-build' if native else 'wasm-build-no-trace' if no_trace else 'wasm-build');build.mkdir(exist_ok=True)
    env=os.environ.copy();env['EM_CONFIG']=str(SDK/'.emscripten');env['EM_CACHE']=str(SDK/'upstream/emscripten/cache')
    compiler=[shutil.which('g++')] if native else [sys.executable,str(SDK/'upstream/emscripten/em++.py')]
    flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-I'+str(SRC),'-I'+str(BOOST)]
    if not native:flags+=['-fexceptions']
    sources=[p for p in SRC.glob('*.cpp') if p.stem!='parallel_progress']+[ROOT/'research/native/whole_run_worker.cpp']
    def compile_one(p):
        obj=build/(p.stem+'.o');sig=hashlib.sha256((p.read_text()+json.dumps(flags)+json.dumps(changes)).encode()).hexdigest();stamp=obj.with_suffix('.sig')
        if not obj.exists() or not stamp.exists() or stamp.read_text()!=sig:
            r=subprocess.run([*compiler,*flags,'-c',str(p),'-o',str(obj)],env=env,capture_output=True,text=True)
            if r.returncode:raise RuntimeError(p.name+'\n'+r.stderr[-10000:])
            stamp.write_text(sig)
        print(p.name,flush=True);return obj
    with ThreadPoolExecutor(max_workers=3) as pool:objects=list(pool.map(compile_one,sources))
    target=BASE/('whole_run_type_cache.mjs' if type_cache else 'whole_run_adaptive.mjs' if adaptive else 'whole_run.exe' if native else 'whole_run_no_trace.mjs' if no_trace else 'whole_run.mjs')
    link=['-static-libgcc','-static-libstdc++'] if native else ['--no-entry','-fexceptions','-sDISABLE_EXCEPTION_CATCHING=0','-sMODULARIZE=1','-sEXPORT_ES6=1','-sENVIRONMENT=web,worker,node','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=1048576','-sEXPORTED_FUNCTIONS=["_wr_init","_wr_ligand","_wr_run","_wr_memory"]','-sEXPORTED_RUNTIME_METHODS=["ccall","FS"]']
    if adaptive:link=[x.replace('"_wr_memory"]','"_wr_memory","_wr_refine"]') for x in link]
    subprocess.run([*compiler,*flags,*map(str,objects),*link,'-o',str(target)],env=env,check=True)
    record={'engine':'Vina 1.2.7 pinned upstream; direct unit seed; sequential CPU1; no_refine=true','compiler':subprocess.check_output([*compiler,'--version'],env=env,text=True).splitlines()[0],'flags':flags,'link':link,'patches':changes,'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    if not native:record['wasm_sha256']=hashlib.sha256(target.with_suffix('.wasm').read_bytes()).hexdigest()
    destination=ROOT/'docs/evaluation/adaptive_docking_2026-09-08' if adaptive else OUT
    destination.mkdir(parents=True,exist_ok=True)
    (destination/('build_wasm_type_cache.json' if type_cache else 'build_wasm_adaptive.json' if adaptive else 'build_native.json' if native else 'build_wasm_no_trace.json' if no_trace else 'build_wasm.json')).write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':main()
