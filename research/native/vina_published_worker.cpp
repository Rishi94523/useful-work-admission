#include "vina.h"
#include "vina_task_io.h"
#include <sstream>
int split_mode=0,split_index=0,split_evals=0,split_steps=0;
std::string split_folder;std::vector<double> split_trace;
int main(int argc,char** argv){
 if(argc!=10)return 2;
 try{
  Vina v("vina",1,104729,0,false);v.set_receptor(argv[1]);v.set_ligand_from_file(argv[3]);v.compute_vina_maps(std::stod(argv[4]),std::stod(argv[5]),std::stod(argv[6]),std::stod(argv[7]),std::stod(argv[8]),std::stod(argv[9]),0.375);v.save_initial();
  std::cout<<"READY"<<std::endl;
  std::string line;while(std::getline(std::cin,line)){
   if(line=="QUIT")break;
   std::istringstream in(line);int seed,e,cap,poses;std::string output;
   if(!(in>>split_mode>>split_index>>seed>>e>>cap>>poses>>split_folder>>output))return 3;
   if(split_mode<0||split_mode>2||e<1||e>512||split_index<0||split_index>=e||cap<0||poses<1||poses>20)return 4;
   v.restore_initial(seed);auto t=std::chrono::steady_clock::now();v.global_search(e,poses,1.0,cap);
   double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();
   std::cout<<std::setprecision(17)<<"{\"ms\":"<<ms;
   if(split_mode!=1){v.write_poses(output,poses,1000);auto energies=v.get_poses_energies(poses,1000);std::cout<<",\"score\":"<<energies.at(0).at(0)<<",\"poses\":"<<energies.size();}
   std::cout<<"}"<<std::endl;
  }
 }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}
}
