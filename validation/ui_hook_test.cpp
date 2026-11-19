#include "loader.h"
#include "resident_ui.h"
#include <cassert>
#include <cstdio>
#include <array>
static uint32_t hash(const char* s){uint32_t v=5381;for(;*s;++s){char c=*s;if(c>='A'&&c<='Z')c+=32;v=v*33+uint8_t(c);}return v;}
int main(int argc,char** argv){assert(argc==2);
 for(uint32_t base:{STOCK_BASE,0x48000000u}){
  std::string error;auto cpu=Cpu::CreateUnicorn(&error);assert(cpu);S3EBinary bin;assert(LoadS3E(argv[1],bin));assert(SetupSandbox(cpu.get(),bin,base));assert(cpu->MemMap(0x60000000,4096)==0);
  ResidentUi ui(cpu.get());assert(ui.Install());auto put=[&](uint32_t a,uint32_t v){assert(cpu->MemWrite(a,&v,4)==0);};
  uint32_t object=0x60000100,right=0x60000300,left=0x60000400,stop=0x60000800;
  put(object,G(0x4a0ed154));put(object+12,8);put(object+0x8c,right);put(object+0x90,left);put(right+12,8);put(left+12,8);
  struct Row{const char* left;const char* right;uint32_t expected;};
  const Row cases[]={{"Next","Skip",5},{"Select","Back",5},{"Examine","Cancel",5},{"Move","EndGame",5},{"Upgrade","Quit",5},{"Retry","Continue",10},{"Knife","Pause",48},{"ExitAim","Pause",80},{"Clear","Back",4}};
  for(auto r:cases){char a[80],b[80];snprintf(a,sizeof(a),"ID_SoftKeyLabel_%s",r.left);snprintf(b,sizeof(b),"ID_SoftKeyLabel_%s",r.right);put(object+0x9c,hash(b));put(object+0xa0,hash(a));
   uint32_t sp=STACK_BASE+STACK_SIZE-256,cpsr=0x30;cpu->RegWrite(Cpu::REG_CPSR,&cpsr);cpu->RegWrite(Cpu::REG_SP,&sp);cpu->RegWrite(0,&object);cpu->RegWrite(Cpu::REG_LR,&stop);assert(cpu->Start(G(0x4a04d058)|1,stop,1000)==0);assert(ui.Take()==r.expected);assert(ui.Take()==0);
  }
  puts("PASS: localized context IDs, left/right placement, drawing suppression and per-frame reset");
 }
}
