// Reference CLI translation unit: supplies the split-instrumentation globals so
// the official Vina main can link against the patched task library unchanged.
// split_mode 0 is the ordinary whole-run path; the task files it writes are a
// side effect of the instrumentation and do not participate in the search.
#include <cstdlib>
#include <string>
#include <vector>
int split_mode=0,split_index=0,split_evals=0,split_steps=0;
std::vector<double> split_trace;
static std::string folder(){const char* e=std::getenv("VINA_SPLIT_FOLDER");return e?std::string(e):std::string(".");}
std::string split_folder=folder();
