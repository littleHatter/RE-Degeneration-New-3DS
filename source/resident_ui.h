#pragma once
#include "cpu.h"
#include "loader.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
// Observe the visible softkey frame at its render boundary, independent of language.
class ResidentUi {
 Cpu* cpu;uint32_t pending=0;
 uint32_t word(uint32_t a){uint32_t v=0;cpu->MemRead(a,&v,4);return v;}
 static uint32_t hash(const char* s){uint32_t v=5381;for(;*s;++s){char c=*s;if(c>='A'&&c<='Z')c+=32;v=v*33+uint8_t(c);}return v;}
 uint32_t classify(uint32_t id,bool right){
  struct M{const char* name;uint32_t flag;};
  static const M left[]={{"Next",1},{"Select",1},{"Examine",1},{"Move",1},{"Level",1},{"Upgrade",1},{"Retry",2},{"Knife",32},{"ExitAim",64}};
  static const M rhs[]={{"Skip",4},{"Back",4},{"Cancel",4},{"EndGame",4},{"Quit",4},{"Continue",8},{"Pause",16}};
  auto find=[&](const M* p,size_t n)->uint32_t{for(size_t i=0;i<n;++i){char name[80];snprintf(name,sizeof(name),"ID_SoftKeyLabel_%s",p[i].name);if(hash(name)==id)return p[i].flag;}return 0u;};
  return right?find(rhs,sizeof(rhs)/sizeof(*rhs)):find(left,sizeof(left)/sizeof(*left));
 }
 static void Draw(Cpu* c,uint64_t,uint32_t,void* u){
  auto& s=*static_cast<ResidentUi*>(u);uint32_t object=0;c->RegRead(0,&object);
  if(s.word(object)!=G(0x4a0ed154))return;
  // Visibility bit 8 must still be set: hidden frames must not leave stale prompts.
  uint32_t flags=s.word(object+12);if(!(flags&8))return;
  uint32_t a=s.word(object+0x8c),b=s.word(object+0x90);
  if(a&&(s.word(a+12)&8))s.pending|=s.classify(s.word(object+0x9c),true);
  if(b&&(s.word(b+12)&8))s.pending|=s.classify(s.word(object+0xa0),false);
  if(getenv("RE_UI_TRACE")){static uint32_t old=~0u;if(old!=s.pending){fprintf(stderr,"[ConsoleUI] right=%08x left=%08x prompts=%u\n",s.word(object+0x9c),s.word(object+0xa0),s.pending);old=s.pending;}}
  uint32_t lr=0,cpsr=0;c->RegRead(Cpu::REG_LR,&lr);c->RegRead(Cpu::REG_CPSR,&cpsr);cpsr=(cpsr&~32u)|((lr&1)?32u:0u);c->RegWrite(Cpu::REG_CPSR,&cpsr);c->RegWrite(Cpu::REG_PC,&lr);
 }
public:
 explicit ResidentUi(Cpu* c):cpu(c){}
 bool Install(){return word(G(0x4a0ed188))==(G(0x4a04d058)|1)&&cpu->AddCodeHook(Draw,this,G(0x4a04d058),G(0x4a04d058))==Cpu::OK;}
 uint32_t Take(){uint32_t v=pending;pending=0;return v;}
};
