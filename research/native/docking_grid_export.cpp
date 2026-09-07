// Trusted preprocessing and independent score oracle for a finite rigid search.
// Uses the pinned Vina library; does not replace or prove its global search.
#include "vina.h"
#include "parse_pdbqt.h"
#include <chrono>
#include <iomanip>
#include <string>
#include <fstream>
#include <sstream>
std::string convert_XS_to_string(sz t);
int main(int argc,char**argv){
    if(argc!=10)return 2;
    Vina v("vina",1,104729,0,true); // no_refine: score against maps, not explicit receptor.
    const auto begin=std::chrono::steady_clock::now();
    v.set_receptor(argv[1]);v.set_ligand_from_file(argv[2]);
    v.compute_vina_maps(std::stod(argv[3]),std::stod(argv[4]),std::stod(argv[5]),
        std::stod(argv[6]),std::stod(argv[7]),std::stod(argv[8]),.375,true);
    v.write_maps(argv[9]);
    // The exchanged maps are the scientific input, including their serialized
    // precision. Reload them so the independent oracle checks that same input.
    v.load_maps(argv[9]);
    model ligand=parse_ligand_pdbqt_from_file(argv[2],atom_type::XS);
    std::cout<<std::setprecision(17)<<"{\"preparation_ms\":"<<std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count()<<",\"atoms\":[";
    bool first=true;
    for(sz i=0;i<ligand.num_movable_atoms();i++){
        const auto atom=ligand.get_atom(i);const auto t=atom.get(atom_type::XS);
        if(t>=num_atom_types(atom_type::XS))continue;
        const auto xyz=ligand.get_coords(i);if(!first)std::cout<<",";first=false;
        std::cout<<"{\"type\":\""<<convert_XS_to_string(t)<<"\",\"xyz\":["<<xyz[0]<<","<<xyz[1]<<","<<xyz[2]<<"]}";
    }
    std::cout<<"]}"<<std::endl;
    std::string path;
    while(std::getline(std::cin,path)){
        if(path=="QUIT")break;
        if(path.size()>4096)return 3;
        try{
            std::ifstream file(path);std::ostringstream buffer;buffer<<file.rdbuf();
            if(!file)throw std::runtime_error("Missing generated pose");
            v.set_ligand_pose_cached(buffer.str());
            const auto energy=v.score();
            std::cout<<"{\"ok\":true,\"score\":"<<energy[0]<<",\"energies\":[";
            for(std::size_t i=0;i<energy.size();i++){if(i)std::cout<<",";std::cout<<energy[i];}
            std::cout<<"]}"<<std::endl;
        }catch(...){std::cout<<"{\"ok\":false}"<<std::endl;}
    }
}
