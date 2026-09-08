// Research-only multi-ligand Vina map/export and baseline oracle. Trusted IPC.
#include "vina.h"
#include "parse_pdbqt.h"
#include <chrono>
#include <iomanip>
#include <fstream>
#include <sstream>
std::string convert_XS_to_string(sz t);
std::string json_string(const std::string& s){std::ostringstream o;o<<'"';for(unsigned char c:s){if(c=='"'||c=='\\')o<<'\\'<<c;else if(c=='\n')o<<"\\n";else if(c=='\r')o<<"\\r";else if(c=='\t')o<<"\\t";else if(c<32)o<<'?';else o<<c;}o<<'"';return o.str();}
int main(int argc,char**argv){
 if(argc!=9)return 2;
 Vina v("vina",1,104729,0,true);v.set_receptor(argv[1]);
 const auto start=std::chrono::steady_clock::now();
 v.compute_vina_maps(std::stod(argv[2]),std::stod(argv[3]),std::stod(argv[4]),std::stod(argv[5]),std::stod(argv[6]),std::stod(argv[7]),.375,true);
 v.write_maps(argv[8]);v.load_maps(argv[8]);
 std::cout<<std::setprecision(17)<<"{\"ready\":true,\"map_prepare_ms\":"<<std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count()<<"}"<<std::endl;
 std::string line;
 while(std::getline(std::cin,line)){
  if(line=="QUIT")break;if(line.size()>8192)return 3;
  std::istringstream in(line);std::string mode,path,out;int e=1,evals=1000;in>>mode>>std::quoted(path);
  try{
   if(mode=="META"){
    model m=parse_ligand_pdbqt_from_file(path,atom_type::XS);
    std::cout<<"{\"atoms\":[";bool first=true;
    for(sz i=0;i<m.num_movable_atoms();i++){
     const auto a=m.get_atom(i);auto t=a.get(atom_type::XS);if(t>=num_atom_types(atom_type::XS))continue;
     // Match Vina cache::eval handling of macrocycle closure pseudo-atoms.
     switch(t){
      case XS_TYPE_G0:case XS_TYPE_G1:case XS_TYPE_G2:case XS_TYPE_G3:continue;
      case XS_TYPE_C_H_CG0:case XS_TYPE_C_H_CG1:case XS_TYPE_C_H_CG2:case XS_TYPE_C_H_CG3:t=XS_TYPE_C_H;break;
      case XS_TYPE_C_P_CG0:case XS_TYPE_C_P_CG1:case XS_TYPE_C_P_CG2:case XS_TYPE_C_P_CG3:t=XS_TYPE_C_P;break;
     }
     auto p=m.get_coords(i);if(!first)std::cout<<",";first=false;
     std::cout<<"{\"type\":\""<<convert_XS_to_string(t)<<"\",\"xyz\":["<<p[0]<<","<<p[1]<<","<<p[2]<<"]}";
    }std::cout<<"]}"<<std::endl;
   }else if(mode=="LOAD"){
    // Stream safely on Windows: upstream get_file_contents sizes a text-mode
    // read using a byte-position, which is unsafe for some CRLF files.
    std::ifstream f(path);std::ostringstream b;b<<f.rdbuf();if(!f)throw std::runtime_error("missing ligand");
    v.set_ligand_from_string(b.str());std::cout<<"{\"ok\":true}"<<std::endl;
   }else{
    std::ifstream f(path);std::ostringstream b;b<<f.rdbuf();if(!f)throw std::runtime_error("missing pose");
    auto begin=std::chrono::steady_clock::now();v.set_ligand_pose_cached(b.str());
    if(mode=="DOCK"){
     in>>e>>evals>>std::quoted(out);if(!in||e<1||e>16||evals<0)throw std::runtime_error("bad search");
     v.global_search(e,1,1.0,evals);auto energy=v.get_poses_energies(1,1000).at(0);v.write_poses(out,1,1000);
     std::cout<<"{\"ok\":true,\"score\":"<<energy[0];
    }else if(mode=="SCORE"){
     auto energy=v.score();std::cout<<"{\"ok\":true,\"score\":"<<energy[0]<<",\"grid_energy\":"<<energy[1];
    }else throw std::runtime_error("bad mode");
    std::cout<<",\"compute_and_pose_prepare_ms\":"<<std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count()<<"}"<<std::endl;
   }
  }catch(const std::exception& error){std::cout<<"{\"ok\":false,\"error\":"<<json_string(error.what())<<"}"<<std::endl;}
   catch(...){std::cout<<"{\"ok\":false,\"error\":\"native exception\"}"<<std::endl;}
 }
}
