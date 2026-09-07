// Research-only persistent wrapper around pinned AutoDock Vina 1.2.7.
// Adds guarded reuse of same-ligand interaction tables; scoring formulas unchanged.
// Receives paths to locally validated inputs, not a public network protocol.
#include "vina.h"
#include <chrono>
#include <fstream>
#include <iomanip>
#include <sstream>

using Clock = std::chrono::steady_clock;
double millis(Clock::time_point a, Clock::time_point b) {
    return std::chrono::duration<double, std::milli>(b-a).count();
}

int main(int argc, char** argv) {
    if (argc != 10) return 2;
    std::cout << std::setprecision(17);
    const auto start=Clock::now();
    Vina vina("vina",1,std::stoi(argv[9]),0,false);
    vina.set_receptor(argv[1]);
    vina.set_ligand_from_file(argv[2]);
    vina.compute_vina_maps(std::stod(argv[3]),std::stod(argv[4]),std::stod(argv[5]),
        std::stod(argv[6]),std::stod(argv[7]),std::stod(argv[8]),0.375);
    std::cout << "{\"ready\":true,\"setup_ms\":" << millis(start,Clock::now()) << "}" << std::endl;
    std::string line;
    while (std::getline(std::cin,line)) {
        if (line=="QUIT") break;
        if (line.size()>8192) return 3;
        std::istringstream command(line);
        std::string mode, filename, output;
        int exhaustiveness=1,max_evals=1000;
        command >> mode >> std::quoted(filename) >> exhaustiveness >> max_evals >> std::quoted(output);
        if (!command || (mode!="S" && mode!="D") || exhaustiveness<1 || exhaustiveness>32 || max_evals<0) return 4;
        try {
            const auto a=Clock::now();
            std::ifstream input(filename);
            std::ostringstream contents; contents << input.rdbuf();
            if (!input || contents.str().size()>16384) throw vina_runtime_error("Invalid bounded input");
            vina.set_ligand_pose_cached(contents.str());
            const auto b=Clock::now();
            std::vector<double> energies;
            if (mode=="S") energies=vina.score();
            else {
                vina.global_search(exhaustiveness,1,1.0,max_evals);
                energies=vina.get_poses_energies(1,3.0).at(0);
                vina.write_poses(output,1,3.0);
            }
            const auto c=Clock::now();
            std::cout << "{\"ok\":true,\"score\":" << energies.at(0)
                << ",\"parse_prepare_ms\":" << millis(a,b)
                << ",\"compute_ms\":" << millis(b,c)
                << ",\"job_ms\":" << millis(a,c) << "}" << std::endl;
        } catch (const std::exception& error) {
            const std::string message=error.what();
            const char* kind=message.find("outside")!=std::string::npos?"outside_grid":message.find("atom type")!=std::string::npos?"cache_atom_type_mismatch":"engine_error";
            std::cout << "{\"ok\":false,\"error\":\"" << kind << "\"}" << std::endl;
        }
    }
    return 0;
}
