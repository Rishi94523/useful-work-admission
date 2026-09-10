// Research task transport: round-trip doubles, raw minima before global merge.
// Fixed input model determines all dimensions; no client-controlled allocation.
#pragma once
#include <fstream>
#include <iomanip>
#include <chrono>
#include "conf.h"
extern int split_mode, split_index, split_evals, split_steps;
extern std::string split_folder;
extern std::vector<double> split_trace;
inline void task_write(const std::string& path,const output_container& out){
 std::ofstream f(path); f<<std::setprecision(17)<<out.size()<<'\n';
 for(const auto& o:out){
  f<<o.e<<' ';
  for(const auto& l:o.c.ligands){for(int k=0;k<3;k++)f<<l.rigid.position[k]<<' ';auto q=l.rigid.orientation;f<<q.R_component_1()<<' '<<q.R_component_2()<<' '<<q.R_component_3()<<' '<<q.R_component_4()<<' ';for(auto t:l.torsions)f<<t<<' ';}
  for(const auto& r:o.c.flex)for(auto t:r.torsions)f<<t<<' ';
  f<<o.coords.size()<<' ';for(const auto& p:o.coords)for(int k=0;k<3;k++)f<<p[k]<<' ';f<<'\n';
 }
 if(!f)throw std::runtime_error("task write failed");
}
inline void task_read(const std::string& path,output_container& out,const conf_size& size,sz atoms,sz limit){
 std::ifstream f(path);sz n;if(!(f>>n)||n>limit)throw std::runtime_error("invalid task count");
 for(sz i=0;i<n;i++){
  output_type o(conf(size),0);f>>o.e;
  for(auto& l:o.c.ligands){for(int k=0;k<3;k++)f>>l.rigid.position[k];double a,b,c,d;f>>a>>b>>c>>d;l.rigid.orientation=qt(a,b,c,d);for(auto& t:l.torsions)f>>t;}
  for(auto& r:o.c.flex)for(auto& t:r.torsions)f>>t;
  sz count;f>>count;if(count!=atoms)throw std::runtime_error("invalid task atom count");o.coords.resize(count);for(auto& p:o.coords)for(int k=0;k<3;k++)f>>p[k];
  if(!f||!std::isfinite(o.e))throw std::runtime_error("invalid task record");out.push_back(new output_type(o));
 }
 std::string extra;if(f>>extra)throw std::runtime_error("trailing task data");
}
