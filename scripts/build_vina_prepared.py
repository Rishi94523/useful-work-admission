"""Isolated lossless prepared maps/type-table codec; reference build untouched."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'tmp/vina-prepared';src=base/'source';src.mkdir(parents=True,exist_ok=True)
for p in (ROOT/'tmp/vina-resources/compact_single/source').iterdir():
 if p.is_file():shutil.copyfile(p,src/p.name)
(src/'prepared_io.h').write_text(r'''
#pragma once
#include <fstream>
#include <cstdint>
#include <stdexcept>
#include <cmath>
template<class T> void ps_write(std::ostream& o,const T& x){o.write(reinterpret_cast<const char*>(&x),sizeof(x));if(!o)throw std::runtime_error("prepared write");}
template<class T> T ps_read(std::istream& i){T x;i.read(reinterpret_cast<char*>(&x),sizeof(x));if(!i)throw std::runtime_error("truncated prepared state");return x;}
inline void ps_bytes(std::istream& i,void* p,size_t n){i.read(static_cast<char*>(p),n);if(!i)throw std::runtime_error("truncated prepared array");}
''')
p=src/'cache.h';s=p.read_text();s=s.replace('#include <iostream>','#include <iostream>\n#include "prepared_io.h"')
s=s.replace('private:\n\tgrid_dims m_gd;',r'''
 void prepared_write(std::ostream& o) const{
  for(sz a=0;a<3;a++){ps_write(o,m_gd[a].begin);ps_write(o,m_gd[a].end);ps_write(o,uint32_t(m_gd[a].n_voxels));}
  ps_write(o,m_slope);ps_write(o,uint32_t(m_grids.size()));
  for(const auto& g:m_grids){ps_write(o,uint32_t(g.initialized()));if(g.initialized())o.write(reinterpret_cast<const char*>(&g.m_data(0,0,0)),g.m_data.dim0()*g.m_data.dim1()*g.m_data.dim2()*sizeof(fl));}
 }
 void prepared_read(std::istream& i){
  for(sz a=0;a<3;a++){m_gd[a].begin=ps_read<fl>(i);m_gd[a].end=ps_read<fl>(i);m_gd[a].n_voxels=ps_read<uint32_t>(i);if(!std::isfinite(m_gd[a].begin)||!std::isfinite(m_gd[a].end)||m_gd[a].end<=m_gd[a].begin||m_gd[a].n_voxels<1||m_gd[a].n_voxels>128)throw std::runtime_error("prepared dimensions");}
  m_slope=ps_read<fl>(i);if(m_slope!=1e6||ps_read<uint32_t>(i)!=m_grids.size())throw std::runtime_error("prepared grid schema");
  for(auto& g:m_grids){auto present=ps_read<uint32_t>(i);if(present>1)throw std::runtime_error("prepared flag");if(present){g.init(m_gd);ps_bytes(i,&g.m_data(0,0,0),g.m_data.dim0()*g.m_data.dim1()*g.m_data.dim2()*sizeof(fl));}}
 }
private:
 grid_dims m_gd;''');p.write_text(s)
p=src/'precalculate.h';s=p.read_text();s='#include "prepared_io.h"\n'+s
s=s.replace('    prv smooth;',r'''
    void prepared_write(std::ostream& o) const{
      ps_write(o,uint32_t(fast.size()));ps_write(o,factor);
      if(!fast.empty())o.write(reinterpret_cast<const char*>(fast.data()),fast.size()*sizeof(fl));
      for(const auto& p:smooth){ps_write(o,p.first);ps_write(o,p.second);}
    }
    void prepared_read(std::istream& i,sz expected){
      auto n=ps_read<uint32_t>(i);auto f=ps_read<fl>(i);
      if((n!=0&&n!=expected)||f!=factor)throw std::runtime_error("prepared table schema");
      fast.resize(n);smooth.resize(n);if(n)ps_bytes(i,fast.data(),n*sizeof(fl));
      for(auto& p:smooth){p.first=ps_read<fl>(i);p.second=ps_read<fl>(i);}
    }
    prv smooth;''',1)
s=s.replace('    precalculate() { }',r'''
    void prepared_write(std::ostream& o) const{
      ps_write(o,uint32_t(m_data.dim()));for(sz k=0;k<m_data.dim()*(m_data.dim()+1)/2;k++)m_data(k).prepared_write(o);
    }
    void prepared_read(std::istream& i){
      if(ps_read<uint32_t>(i)!=m_data.dim())throw std::runtime_error("prepared type count");
      for(sz k=0;k<m_data.dim()*(m_data.dim()+1)/2;k++)m_data(k).prepared_read(i,m_n);
    }
    precalculate() { }''',1);p.write_text(s)
p=src/'vina.h';s=p.read_text();s=s.replace('void compute_vina_maps(', 'void prepared_save(const std::string& path);\n void prepared_load(const std::string& path);\n void compute_vina_maps(',1);p.write_text(s)
p=src/'vina.cpp';s=p.read_text();s+=r'''
void Vina::prepared_save(const std::string& path){
 if(!m_map_initialized)throw std::runtime_error("maps absent");std::ofstream o(path,std::ios::binary);
 ps_write(o,uint32_t(0x31535056));m_grid.prepared_write(o);m_precalculated_sf.prepared_write(o);if(!o)throw std::runtime_error("prepared write");
}
void Vina::prepared_load(const std::string& path){
 if(!m_receptor_initialized||!m_ligand_initialized||m_sf_choice!=SF_VINA)throw std::runtime_error("prepared input state");
 std::ifstream i(path,std::ios::binary);if(ps_read<uint32_t>(i)!=0x31535056)throw std::runtime_error("prepared version");
 cache grid;grid.prepared_read(i);
 if(!grid.are_atom_types_grid_initialized(m_model.get_movable_atom_types(m_scoring_function->get_atom_typing())))throw std::runtime_error("prepared missing type");
 precalculate tables(*m_scoring_function);tables.prepared_read(i);if(i.peek()!=std::char_traits<char>::eof())throw std::runtime_error("prepared trailing data");
 m_precalculated_sf=std::move(tables);m_grid=std::move(grid);
 if(!m_no_refine){non_cache nc(m_model,m_grid.gd(),&m_precalculated_sf,1e6);m_non_cache=nc;}
 m_map_initialized=true;
}
''';p.write_text(s)
p=src/'browser_probe.cpp';s=p.read_text();s=s.replace('unsigned vt_memory()',r'''
const char* vt_prepare(){try{engine->prepared_save("/prepared.bin");answer="{\"ok\":true}";}catch(...){answer="{\"ok\":false}";}return answer.c_str();}
const char* vt_restore(){try{engine.reset(new Vina("vina",1,104729,0,false));engine->set_receptor("/receptor.pdbqt");engine->set_ligand_from_file("/ligand.pdbqt");engine->prepared_load("/prepared.bin");engine->save_initial();answer="{\"ok\":true}";}catch(...){engine.reset();answer="{\"ok\":false}";}return answer.c_str();}
unsigned vt_memory()''');p.write_text(s)
sdk=ROOT/'tmp/docking-runs/emsdk';env={**os.environ,'EM_CONFIG':str(sdk/'.emscripten'),'EM_CACHE':str(sdk/'upstream/emscripten/cache')}
compiler=[sys.executable,str(sdk/'upstream/emscripten/em++.py')];flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-fexceptions','-I'+str(src),'-I'+str(ROOT/'tmp/docking-pilot/boost/ucrt64/include')]
def compile(p):
 obj=base/(p.stem+'.o');r=subprocess.run([*compiler,*flags,'-c',str(p),'-o',str(obj)],env=env,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-4000:])
 return obj
with ThreadPoolExecutor(max_workers=3) as pool:objects=list(pool.map(compile,[p for p in src.glob('*.cpp') if p.stem!='parallel_progress']))
exports=['vt_init','vt_run','vt_memory','vt_seeds','vt_profile','vt_finalize','vt_prepare','vt_restore']
link=['--no-entry','-fexceptions','-sDISABLE_EXCEPTION_CATCHING=0','-sMODULARIZE=1','-sEXPORT_ES6=1','-sENVIRONMENT=web,worker,node','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=1048576','-sEXPORTED_FUNCTIONS='+json.dumps(['_'+x for x in exports]),'-sEXPORTED_RUNTIME_METHODS=["ccall","FS"]']
subprocess.run([*compiler,*flags,*map(str,objects),*link,'-o',str(base/'vina_tasks.mjs')],env=env,check=True)
out=ROOT/'docs/evaluation/vina_prepared_2026-09-13';out.mkdir(parents=True,exist_ok=True)
(out/'build.json').write_text(json.dumps({'reference_wasm_sha256':hashlib.sha256((ROOT/'tmp/vina-resources/compact_single/vina_tasks.wasm').read_bytes()).hexdigest(),'wasm_sha256':hashlib.sha256((base/'vina_tasks.wasm').read_bytes()).hexdigest(),'flags':flags,'link':link},indent=2)+'\n')
print('Prepared build complete',flush=True)
