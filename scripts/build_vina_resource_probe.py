"""Isolated, phase-instrumented WASM builds; reference task source untouched."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
variant=sys.argv[1] if len(sys.argv)>1 else 'baseline'
assert variant in ['baseline','moves','compact','compact_single']
base=ROOT/'tmp/vina-resources'/variant; src=base/'source'; src.mkdir(parents=True,exist_ok=True)
for p in (ROOT/'tmp/vina-tasks/source').iterdir():
 if p.is_file():shutil.copyfile(p,src/p.name)
for name in ['precalculate.h','vina.cpp']:
 p=src/name;s=p.read_text();s='void resource_mark(const char*);\n'+s
 if name=='precalculate.h':
  s=s.replace('m_data = data;', 'resource_mark("table_before_store");\n        m_data = '+('std::move(data)' if variant!='baseline' else 'data')+';\n        resource_mark("table_after_store");')
  if variant.startswith('compact'):
   # Vina/Vinardo atom potentials depend on XS type. AD4 depends on charge:
   # fail closed rather than silently applying this specialization to AD4.
   before,byatom=s.split('struct precalculate_byatom',1)
   byatom=byatom.replace('sz n_atoms = model.num_atoms();\n        atomv atoms = model.get_atoms();', '''
        if(sf.get_atom_typing()!=atom_type::XS)throw std::runtime_error("compact probe requires XS scoring");
        atomv original=model.get_atoms(),atoms;
        for(const auto& a:original){sz i=0;for(;i<atoms.size();i++)if(atoms[i].xs==a.xs)break;if(i==atoms.size())atoms.push_back(a);atom_lookup.push_back(i);}
        sz n_atoms=atoms.size();''')
   byatom=byatom.replace('return m_data(i, j).eval_', 'return m_data(m_data.index_permissive(atom_lookup[i],atom_lookup[j])).eval_')
   byatom=byatom.replace('return m_data.index_permissive(t1, t2);','return m_data.index_permissive(atom_lookup[t1], atom_lookup[t2]);')
   byatom=byatom.replace('triangular_matrix<precalculate_element> m_data;', 'szv atom_lookup;\n    triangular_matrix<precalculate_element> m_data;')
   # Lazy type tables retain identical resolution/cutoff/values and compute a
   # table before its first use. The scoring function is owned by Vina.
   before=before.replace('triangular_matrix<precalculate_element> data(num_atom_types(sf.get_atom_typing()), precalculate_element(m_n, m_factor));','m_sf=&sf; m_v=v;\n        triangular_matrix<precalculate_element> data(num_atom_types(sf.get_atom_typing()), precalculate_element(0, m_factor));')
   start=before.index('        VINA_FOR(t1, data.dim())');end=before.index('        resource_mark("table_before_store")',start)
   before=before[:start]+before[end:]
   before=before.replace('return m_data(type_pair_index).eval_', 'return ensure(type_pair_index).eval_')
   before=before.replace('triangular_matrix<precalculate_element> m_data;', '''
    const ScoringFunction* m_sf=nullptr;fl m_v;
    mutable triangular_matrix<precalculate_element> m_data;
    const precalculate_element& ensure(sz idx) const{
      auto& p=m_data(idx);if(!p.smooth.empty())return p;
      sz a=0,b=0;bool found=false;
      for(sz i=0;i<m_data.dim()&&!found;i++)for(sz j=i;j<m_data.dim();j++)if(m_data.index(i,j)==idx){a=i;b=j;found=true;break;}
      if(!found)throw std::runtime_error("type table index");
      p=precalculate_element(m_n,m_factor);flv rs=calculate_rs();
      VINA_FOR_IN(k,p.smooth)p.smooth[k].first=(std::min)(m_v,m_sf->eval(a,b,rs[k]));
      p.init_from_smooth_fst(rs);return p;
    }''')
   before=before.replace('m_data(t1, t2).widen(rs, left, right);','{ensure(m_data.index(t1,t2));m_data(t1, t2).widen(rs, left, right);}')
   s=before+'struct precalculate_byatom'+byatom
 else:
  for statement,label in [('m_precalculated_byatom = precalculated_byatom;','ligand_store'),('m_precalculated_sf = precalculated_sf;','type_store'),('m_grid = grid;','grid_store')]:
   replacement=statement
   if variant!='baseline':
    if label=='type_store':replacement='m_precalculated_sf = std::move(precalculated_sf);'
    elif label=='ligand_store':replacement='m_precalculated_byatom = std::move(precalculated_byatom);'
    else:replacement='m_grid = std::move(grid);'
   s=s.replace(statement,'resource_mark("'+label+'_before");'+replacement+'resource_mark("'+label+'_after");')
  if variant!='baseline':s=s.replace('grid.populate(m_model, precalculated_sf, atom_types);','grid.populate(m_model, m_precalculated_sf, atom_types);')
 p.write_text(s)
if variant=='compact_single':
 p=src/'parallel_mc.cpp';s=p.read_text()
 old='VINA_FOR(i, num_tasks)\n\t\ttask_container.push_back(new parallel_mc_task(m, random_int(0, 1000000, generator)));'
 assert old in s
 s=s.replace(old,'''VINA_FOR(i, num_tasks){
     int child_seed=random_int(0,1000000,generator);
     if(split_mode!=1 || int(i)==split_index)task_container.push_back(new parallel_mc_task(m,child_seed));
   }''')
 s=s.replace('auto& task=task_container[i];const std::string path=split_folder+"/"+std::to_string(i)+".task";', 'auto& task=task_container[i];const sz ordinal=split_mode==1?sz(split_index):i;const std::string path=split_folder+"/"+std::to_string(ordinal)+".task";')
 s=s.replace('if(split_mode==1 && int(i)!=split_index)continue;','')
 p.write_text(s)
worker=(ROOT/'research/native/vina_task_browser.cpp').read_text()
worker=worker.replace('#include <memory>','#include <memory>\n#include <malloc.h>')
worker=worker.replace('extern "C" {',r'''
static std::vector<std::string> snapshots;
void resource_mark(const char* phase){
 auto m=mallinfo();std::ostringstream s;
 s<<"{\"phase\":\""<<phase<<"\",\"heap_bytes\":"<<emscripten_get_heap_size()<<",\"live_bytes\":"<<m.uordblks<<",\"free_bytes\":"<<m.fordblks<<",\"time_ms\":"<<emscripten_get_now()<<"}";snapshots.push_back(s.str());
}
extern "C" {
const char* vt_profile(){resource_mark("snapshot");std::ostringstream s;s<<'[';for(size_t i=0;i<snapshots.size();i++){if(i)s<<',';s<<snapshots[i];}s<<']';answer=s.str();return answer.c_str();}
''')
worker=worker.replace('#include <emscripten/heap.h>','#include <emscripten/heap.h>\n#include <emscripten/emscripten.h>')
worker=worker.replace('engine.reset(new Vina','resource_mark("before_engine");engine.reset(new Vina')
worker=worker.replace('engine->set_receptor','resource_mark("after_engine");engine->set_receptor')
worker=worker.replace('engine->set_ligand_from_file','resource_mark("after_receptor");engine->set_ligand_from_file')
worker=worker.replace('engine->compute_vina_maps','resource_mark("after_ligand");engine->compute_vina_maps')
worker=worker.replace('engine->save_initial();','resource_mark("after_maps");engine->save_initial();resource_mark("after_save");')
worker=worker.replace('const char* vt_seeds',r'''const char* vt_finalize(int n){
 try{split_mode=2;engine->restore_initial(104729);engine->global_search(n,9,1.,0);engine->write_poses("/final.pdbqt",9,1000);answer="{\"ok\":true}";}
 catch(...){answer="{\"ok\":false}";}return answer.c_str();
}
const char* vt_seeds''')
(src/'browser_probe.cpp').write_text(worker)
sdk=ROOT/'tmp/docking-runs/emsdk';env={**os.environ,'EM_CONFIG':str(sdk/'.emscripten'),'EM_CACHE':str(sdk/'upstream/emscripten/cache')}
compiler=[sys.executable,str(sdk/'upstream/emscripten/em++.py')]
flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-fexceptions','-I'+str(src),'-I'+str(ROOT/'tmp/docking-pilot/boost/ucrt64/include')]
headers=b''.join(p.read_bytes() for p in sorted(src.glob('*.h')))
def compile(p):
 obj=base/(p.stem+'.o');sig=hashlib.sha256(p.read_bytes()+headers+str(flags).encode()).hexdigest();stamp=obj.with_suffix('.sig')
 if not obj.exists() or not stamp.exists() or stamp.read_text()!=sig:
  r=subprocess.run([*compiler,*flags,'-c',str(p),'-o',str(obj)],env=env,capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr[-5000:])
  stamp.write_text(sig)
 return obj
with ThreadPoolExecutor(max_workers=3) as pool:objects=list(pool.map(compile,[p for p in src.glob('*.cpp') if p.stem!='parallel_progress']))
link=['--no-entry','-fexceptions','-sDISABLE_EXCEPTION_CATCHING=0','-sMODULARIZE=1','-sEXPORT_ES6=1','-sENVIRONMENT=web,worker,node','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=1048576','-sEXPORTED_FUNCTIONS=["_vt_init","_vt_run","_vt_memory","_vt_seeds","_vt_profile","_vt_finalize"]','-sEXPORTED_RUNTIME_METHODS=["ccall","FS"]']
subprocess.run([*compiler,*flags,*map(str,objects),*link,'-o',str(base/'vina_tasks.mjs')],env=env,check=True)
out=ROOT/'docs/evaluation/vina_resources_2026-09-10';out.mkdir(parents=True,exist_ok=True)
(out/(variant+'_build.json')).write_text(json.dumps({'variant':variant,'wasm_sha256':hashlib.sha256((base/'vina_tasks.wasm').read_bytes()).hexdigest(),'flags':flags,'link':link},indent=2)+'\n')
print(variant,'built',flush=True)
