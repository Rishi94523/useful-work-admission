// Optimized attacker/central-compute control for the exact integer map objective.
#include <fstream>
#include <vector>
#include <cstdint>
#include <iostream>
#include <chrono>
#include <algorithm>
#include <stdexcept>
using i64=int64_t;using i32=int32_t;
std::vector<i32> read(const char* path){std::ifstream f(path,std::ios::binary|std::ios::ate);if(!f)throw std::runtime_error("input");auto n=f.tellg();if(n<0||n%4)throw std::runtime_error("shape");std::vector<i32> a(size_t(n)/4);f.seekg(0);f.read(reinterpret_cast<char*>(a.data()),n);if(!f)throw std::runtime_error("read");return a;}
i64 floor_div(i64 a,i64 b){i64 q=a/b,r=a%b;return q-(r<0);}
int main(int argc,char**argv){try{
 if(argc!=7)return 2;auto maps=read(argv[1]),bank=read(argv[2]);int start=std::stoi(argv[3]),N=std::stoi(argv[4]),repeats=std::stoi(argv[5]);
 int T=bank[0],Z=bank[1],Y=bank[2],X=bank[3],C=bank[11],A=bank[12],R=bank[13],offset=bank[14];
 if(bank.size()!=size_t(15+R*9+A+C*A*3)||maps.size()!=size_t(T)*Z*Y*X||start<0||N<1||start+N>C*R*512||repeats<1||repeats>20)return 3;
 auto rot=bank.data()+15,types=rot+R*9,conf=types+A;std::vector<i32> out(size_t(N)*A);i64 check=0;
 std::cout<<"{\"ms\":[";
 for(int repeat=0;repeat<repeats;repeat++){
  auto t=std::chrono::steady_clock::now();
  for(int p=0;p<N;p++){
   i64 id=((i64(start)+p)*104729+offset)%(C*R*512);int tr=id%512,ri=(id/512)%R,ci=id/(512*R);auto r=rot+ri*9;
   int shift[3]={tr%8*375-1312,(tr/8)%8*375-1312,(tr/64)%8*375-1312};
   for(int a=0;a<A;a++){
    auto xyz=conf+(ci*A+a)*3;i64 cell[3],frac[3];
    for(int k=0;k<3;k++){
     i64 pos=floor_div(i64(r[k*3])*xyz[0]+i64(r[k*3+1])*xyz[1]+i64(r[k*3+2])*xyz[2]+500000,1000000)+bank[8+k]+shift[k];
     i64 delta=pos*1000-bank[4+k];cell[k]=floor_div(delta,bank[7]);frac[k]=((delta-cell[k]*bank[7])*256+bank[7]/2)/bank[7];
    }
    if(cell[0]<0||cell[1]<0||cell[2]<0||cell[0]>=X-1||cell[1]>=Y-1||cell[2]>=Z-1)return 4;
    i64 val=0;for(int z=0;z<2;z++)for(int y=0;y<2;y++)for(int x=0;x<2;x++){
     i64 w=(x?frac[0]:256-frac[0])*(y?frac[1]:256-frac[1])*(z?frac[2]:256-frac[2]);
     val+=i64(maps[((types[a]*Z+cell[2]+z)*Y+cell[1]+y)*X+cell[0]+x])*w;
    }
    val=floor_div(val+8388608,16777216);if(val>0)val=(val*10000000+(10000000+val)/2)/(10000000+val);
    if(val<INT32_MIN||val>INT32_MAX)return 5;out[size_t(p)*A+a]=i32(val);
   }
  }
  auto ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-t).count();if(repeat)std::cout<<",";std::cout<<ms;check+=out[repeat%out.size()];
 }
 std::ofstream f(argv[6],std::ios::binary);f.write(reinterpret_cast<const char*>(out.data()),out.size()*4);
 std::cout<<"],\"check\":"<<check<<",\"owned_array_bytes\":"<<(maps.size()+bank.size()+out.size())*4<<"}\n";
 }catch(...){return 10;}}
