// Research C API: pinned Vina searches, reusable maps and ligand preparation.
#include "vina.h"
#include <chrono>
#include <iomanip>
#include <sstream>
#include <memory>
#include <fstream>
#ifdef __EMSCRIPTEN__
#include <emscripten/heap.h>
#endif
int run_direct_seed=0, run_eval_count=0, run_mc_steps=0;
std::vector<double> run_trace;
static std::unique_ptr<Vina> engine;
static std::string result;
static std::string quote(const std::string& s){std::ostringstream o;o<<'"';for(unsigned char c:s){if(c=='"'||c=='\\')o<<'\\'<<c;else if(c=='\n')o<<"\\n";else if(c=='\r')o<<"\\r";else if(c=='\t')o<<"\\t";else if(c<32)o<<'?';else o<<c;}o<<'"';return o.str();}
extern "C" {
unsigned wr_memory(){
#ifdef __EMSCRIPTEN__
 return emscripten_get_heap_size();
#else
 return 0;
#endif
}
const char* wr_ligand(const char* ligand){
 try {if(!engine)throw std::runtime_error("no engine");engine->set_ligand_from_string(ligand);engine->save_initial();result="{\"ok\":true}";}
 catch(...){result="{\"ok\":false,\"error\":\"ligand initialization failure\"}";}return result.c_str();
}
const char* wr_init(const char* maps,const char* ligand){
 try {engine.reset(new Vina("vina",1,104729,0,true));engine->load_maps(maps);engine->set_ligand_from_string(ligand);engine->save_initial();result="{\"ok\":true}";}
 catch(const std::exception& e){result="{\"ok\":false,\"error\":"+quote(e.what())+"}";}catch(...){result="{\"ok\":false,\"error\":\"initialization failure\"}";}
 return result.c_str();
}
const char* wr_run(int seed,int max_evals,int exhaustiveness){
 try {
  if(!engine||seed<=0||max_evals<0||max_evals>1000000||exhaustiveness<1||exhaustiveness>32)throw std::runtime_error("bad bounded run");
  auto t=std::chrono::steady_clock::now();engine->restore_initial(seed);run_direct_seed=exhaustiveness==1?seed:0;run_eval_count=0;run_mc_steps=0;run_trace.clear();
  engine->global_search(exhaustiveness,1,1.0,max_evals);
  const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();
  auto energies=engine->get_poses_energies(1,1000);auto pose=engine->get_poses(1,1000);
  std::ostringstream o;o<<std::setprecision(17)<<"{\"ok\":true,\"score\":"<<energies.at(0).at(0)<<",\"search_ms\":"<<ms<<",\"evals\":"<<run_eval_count<<",\"mc_steps\":"<<run_mc_steps<<",\"pose\":"<<quote(pose)<<",\"trace\":[";
  for(size_t i=0;i<run_trace.size();i++){if(i)o<<',';o<<run_trace[i];}o<<"]}";result=o.str();
 }catch(const std::exception& e){result="{\"ok\":false,\"error\":"+quote(e.what())+"}";}catch(...){result="{\"ok\":false,\"error\":\"search failure\"}";}
 return result.c_str();
}
const char* wr_refine(int max_steps){
 try {
  if(!engine||max_steps<1||max_steps>1000)throw std::runtime_error("bad local bound");
  auto t=std::chrono::steady_clock::now();engine->restore_initial(104729);
  auto energies=engine->optimize(max_steps);
  const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();
  engine->write_pose("/refined.pdbqt");std::ifstream f("/refined.pdbqt");std::ostringstream pose;pose<<f.rdbuf();
  std::ostringstream o;o<<std::setprecision(17)<<"{\"ok\":true,\"score\":"<<energies.at(0)<<",\"search_ms\":"<<ms<<",\"pose\":"<<quote(pose.str())<<"}";result=o.str();
 }catch(const std::exception& e){result="{\"ok\":false,\"error\":"+quote(e.what())+"}";}
 return result.c_str();
}
}
#ifndef __EMSCRIPTEN__
int main(int argc,char** argv){
 if(argc!=3)return 2;std::ifstream f(argv[2]);std::ostringstream b;b<<f.rdbuf();std::cout<<wr_init(argv[1],b.str().c_str())<<std::endl;
 std::string line;while(std::getline(std::cin,line)){
  if(line.rfind("LOAD ",0)==0){std::ifstream f(line.substr(5));std::ostringstream b;b<<f.rdbuf();std::cout<<wr_ligand(b.str().c_str())<<std::endl;}
  else {std::istringstream in(line);int seed,cap,e;if(!(in>>seed>>cap>>e))break;std::cout<<wr_run(seed,cap,e)<<std::endl;}
 }
}
#endif
