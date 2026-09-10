#include "vina.h"
#include "vina_task_io.h"
#include "random.h"
#include <emscripten/heap.h>
#include <memory>
#include <sstream>
int split_mode=1,split_index=0,split_evals=0,split_steps=0;
std::string split_folder="/tasks";std::vector<double> split_trace;
static std::unique_ptr<Vina> engine;static std::string answer;
extern "C" {
unsigned vt_memory(){return emscripten_get_heap_size();}
const char* vt_init(double x,double y,double z){
 try{engine.reset(new Vina("vina",1,104729,0,false));engine->set_receptor("/receptor.pdbqt");engine->set_ligand_from_file("/ligand.pdbqt");engine->compute_vina_maps(x,y,z,30,30,30);engine->save_initial();answer="{\"ok\":true}";}
 catch(...){answer="{\"ok\":false}";}return answer.c_str();
}
const char* vt_run(int index,int n,int cap,int parent_seed){
 try{if(!engine||index<0||index>=n||n>512||n<1||cap<0||parent_seed<=0)throw std::runtime_error("bad unit");split_mode=1;split_index=index;engine->restore_initial(parent_seed);auto t=std::chrono::steady_clock::now();engine->global_search(n,9,1.0,cap);double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();std::ostringstream o;o<<std::setprecision(17)<<"{\"ok\":true,\"total_ms\":"<<ms<<",\"evals\":"<<split_evals<<",\"steps\":"<<split_steps<<"}";answer=o.str();}
 catch(...){answer="{\"ok\":false}";}return answer.c_str();
}
const char* vt_seeds(int n,int parent_seed){
 if(n<1||n>1024||parent_seed<=0){answer="[]";return answer.c_str();}rng generator(static_cast<rng::result_type>(parent_seed));std::ostringstream o;o<<'[';for(int i=0;i<n;i++){if(i)o<<',';o<<random_int(0,1000000,generator);}o<<']';answer=o.str();return answer.c_str();
}
}
