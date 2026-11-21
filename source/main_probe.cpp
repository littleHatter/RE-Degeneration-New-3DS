#include "loader.h"
#include "runtime_s3e.h"
#include "hybrid_trace.h"
#include "stream_checks.h"
#include "desktop_audio_sink.h"
#include "audio_capture.h"
#include "touch_keypad.h"
#include "bottomscreen.h"
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <vector>
#include <algorithm>
#include <cstring>
#include <set>
int main(int argc,char**argv){
 setvbuf(stdout,nullptr,_IONBF,0);
 std::string assets=argc>1?argv[1]:"game",error;
 auto cpu=Cpu::CreateUnicorn(&error);if(!cpu){fprintf(stderr,"%s\n",error.c_str());return 2;}
 S3EBinary bin;if(!LoadS3E(assets+"/resident_evil.xe3u",bin)||!SetupSandbox(cpu.get(),bin,std::getenv("PAN_IMAGE_BASE")?std::strtoul(std::getenv("PAN_IMAGE_BASE"),nullptr,0):STOCK_BASE,64u<<20))return 2;
 for(const auto& p:bin.pointer_fixups){uint32_t actual=0;cpu->MemRead(G(bin.base_addr+p.offset),&actual,4);if(actual!=TRAMPOLINE_BASE+p.func_idx*8){fprintf(stderr,"Type-4 pointer verification failed\n");return 2;}}
 printf("[Probe] Type-4 function pointers patched: %zu\n",bin.pointer_fixups.size());
 auto signedBits=[](uint32_t value,unsigned bits)->int32_t{return int32_t(value<<(32-bits))>>(32-bits);};
 for(const auto& f:bin.arm_fixups){uint32_t insn=0;uint32_t address=G(bin.base_addr+f.offset);cpu->MemRead(address,&insn,4);uint32_t target=address+8+signedBits(insn&0xffffff,24)*4;if(target!=TRAMPOLINE_BASE+f.func_idx*8){fprintf(stderr,"[Verify] ARM import target mismatch\n");return 2;}}
 for(const auto& f:bin.thumb_fixups){uint16_t insn[2]{};uint32_t address=G(bin.base_addr+f.offset);cpu->MemRead(address,insn,4);uint32_t target=((address+4)&~3u)+signedBits(((insn[0]&0x7ff)<<11)|(insn[1]&0x7ff),22)*2;if(target!=TRAMPOLINE_BASE+f.func_idx*8){fprintf(stderr,"[Verify] Thumb import target mismatch\n");return 2;}}
 for(uint32_t offset:bin.relocations){if(offset+4>bin.code_and_data.size()){fprintf(stderr,"[Verify] relocation outside image\n");return 2;}uint32_t original=0,actual=0;std::memcpy(&original,bin.code_and_data.data()+offset,4);cpu->MemRead(G(bin.base_addr+offset),&actual,4);if(actual!=G(original)){fprintf(stderr,"[Verify] absolute relocation mismatch\n");return 2;}}
 fprintf(stderr,"[Verify] ARM=%zu Thumb=%zu pointers=%zu absolute=%zu all targets verified\n",bin.arm_fixups.size(),bin.thumb_fixups.size(),bin.pointer_fixups.size(),bin.relocations.size());

 if(getenv("RE_UI_DIAGNOSTIC")){
 cpu->AddCodeHook([](Cpu* c,uint64_t,uint32_t,void*){uint32_t o=0,v=0,f=0;c->RegRead(0,&o);c->MemRead(o,&v,4);c->MemRead(o+12,&f,4);static std::set<uint32_t> seen;if(seen.insert(v).second)fprintf(stderr,"[UIRenderType] v=%08x flags=%08x object=%08x\n",v,f,o);},nullptr,G(0x4a04d058),G(0x4a04d058));
 cpu->AddCodeHook([](Cpu* c,uint64_t a,uint32_t,void*){uint32_t o=0,t=0,v=0;c->RegRead(0,&o);c->RegRead(1,&t);c->MemRead(o,&v,4);char str[80]{};c->MemRead(t,str,79);static std::set<std::string> seen;if(seen.insert(str).second)fprintf(stderr,"[UISet] at=%08x v=%08x text=%s\n",unsigned(a),v,str);},nullptr,G(0x4a07955c),G(0x4a07955c));
 }
 uint32_t limit=argc>2?std::stoul(argv[2]):30;std::string output=argc>3?argv[3]:"frames",saves=argc>4?argv[4]:"user";
 std::filesystem::create_directories(output);AudioCapture diagnosticAudio;S3ERuntime rt(cpu.get(),assets,saves);rt.Init(bin.imports,bin.config);
 if(const char* path=getenv("RE_AUDIO_CAPTURE")){diagnosticAudio.Open(path);rt.SetAudioCallback([&](const int16_t* p,size_t n,uint32_t rate){diagnosticAudio.Write(p,n,rate,rt.Frames());});}
 BottomScreen bottomPreview;if(const char* path=getenv("RE_BOTTOM_ART"))if(!bottomPreview.Load(path))return 2;
 TouchKeypad touchReplay;bool touchReplayFailed=false;uint32_t keypadState=0;
 if(const char* art=getenv("RE_KEYPAD_TOUCH_REPLAY")){
  if(!touchReplay.Load(art))return 2;
  cpu->AddCodeHook([](Cpu* c,uint64_t,uint32_t,void* user){c->RegRead(0,user);},&keypadState,G(0x4a099ee4),G(0x4a099ee4));
 }
 struct Press{uint32_t first,last,key;};std::vector<Press> input;if(argc>5){std::ifstream f(argv[5]);Press press;while(f>>press.first>>press.last>>press.key)input.push_back(press);}
 rt.SetFrameCallback([&](uint32_t frame,const uint16_t* image,S3ERuntime::Keys& keys){
  if(getenv("RE_UI_DIAGNOSTIC")&&frame==900){uint32_t k[16]{};cpu->MemRead(G(0x4a0f78ec),k,sizeof(k));fprintf(stderr,"[KeyMapping]");for(auto v:k)fprintf(stderr," %u",v);fprintf(stderr,"\n");}
  keys.fill(false);for(auto p:input)if(p.key<256&&frame>=p.first&&frame<p.last)keys[p.key]=true;
  if(getenv("RE_HUD_AUTO")){
   static uint32_t hudAt=0;unsigned green=0;for(unsigned y=211;y<239;++y)for(unsigned x=235;x<310;++x){auto v=image[y*320+x];if(((v>>5)&63)>40&&(v>>11)<10&&(v&31)<20)++green;}
   if(!hudAt&&green>10){hudAt=frame;fprintf(stderr,"[DiagnosticHUD] first playable HUD frame=%u\n",frame);}
   if(hudAt){keys.fill(false);if(getenv("RE_HUD_AUTO_ACTION")&&((frame>=hudAt+30&&frame<hudAt+33)||(frame>=hudAt+120&&frame<hudAt+123)))keys[getenv("RE_HUD_DOOR_ACTION")&&frame>=hudAt+120?208:209]=true;}
  }

  if(getenv("RE_KEYPAD_TOUCH_REPLAY")){
   static uint32_t began=0;bool active=rt.KeypadOpen();if(active&&!began)began=frame;
   unsigned step=began?frame-began:99999;int digit=step==10?3:step==20&&!getenv("RE_KEYPAD_FAST_REPEAT")?1:step==60?9:step==70?11:-1;
   int x=0,y=150;bool down=digit>=0;if(down){auto b=touchReplay.buttons[digit];x=b.x+40;y=b.y+20;}
   int key=touchReplay.Update(active,down,x,y);if(key>=0){rt.QueueKeypadKey(unsigned(key));if(step==10&&getenv("RE_KEYPAD_FAST_REPEAT"))rt.QueueKeypadKey(unsigned(key));}
   if(step>=40&&step<43)keys[209]=true;
   if(step>=90&&step<93)keys[210]=true;
   auto expect=[&](const char* text){char buffer[16]{};cpu->MemRead(keypadState+0x45,buffer,15);if(std::strcmp(buffer,text)){fprintf(stderr,"[TouchReplay] FAIL input mismatch at step=%u\n",step);touchReplayFailed=true;rt.RequestQuit();}else fprintf(stderr,"[TouchReplay] input verified step=%u characters=%zu\n",step,std::strlen(text));};
   if(step==30)expect(getenv("RE_KEYPAD_FAST_REPEAT")?"44":"42");if(step==50)expect("");if(step==80)expect("*#");
   if(step==130){if(rt.KeypadOpen()||rt.QueueKeypadKey(14)){touchReplayFailed=true;rt.RequestQuit();}else fprintf(stderr,"[TouchReplay] PASS digit presses, clear, star/hash, back, and inactive rejection\n");}
   if(active&&(step==10||step==20||step==30||step==80)){
    std::vector<uint16_t> bottom(320*240);touchReplay.Draw(bottom.data());char file[80];snprintf(file,sizeof(file),"/bottom_%06u.ppm",frame);FILE* f=fopen((output+file).c_str(),"wb");if(f){fprintf(f,"P6\n320 240\n255\n");for(int y=0;y<240;++y)for(int x=0;x<320;++x){uint16_t v=bottom[x*240+239-y];unsigned char rgb[]={uint8_t((v>>11)*255/31),uint8_t(((v>>5)&63)*255/63),uint8_t((v&31)*255/31)};fwrite(rgb,1,3,f);}fclose(f);}
   }
  }
  uint32_t consolePrompts=rt.TakeConsolePrompts();
  if(getenv("RE_PROMPT_FRAME_TRACE"))fprintf(stderr,"[PromptFrame] %u %u\n",frame,consolePrompts);
  if(bottomPreview.Ready()&&(frame%30==0||frame==limit)){
   std::vector<uint16_t> fb(320*240);if(rt.KeypadOpen()&&touchReplay.Ready())touchReplay.Draw(fb.data());else bottomPreview.Draw(fb.data(),rt.KeypadOpen()?0:consolePrompts);
   char suffix[64];snprintf(suffix,sizeof(suffix),"/ui_%06u.ppm",frame);FILE* f=fopen((output+suffix).c_str(),"wb");if(f){fprintf(f,"P6\n320 240\n255\n");for(int y=0;y<240;++y)for(int x=0;x<320;++x){auto v=fb[x*240+239-y];unsigned char rgb[]={uint8_t((v>>11)*255/31),uint8_t(((v>>5)&63)*255/63),uint8_t((v&31)*255/31)};fwrite(rgb,1,3,f);}fclose(f);}
  }
  if(getenv("RE_LIVE")&&(frame==1180||frame==1340))rt.RequestDisplayToggle();
  if(frame<=3||frame%30==0||frame==1180||frame==1181||frame==1340||frame==1341||frame==limit){char suffix[64];snprintf(suffix,sizeof(suffix),"/frame_%06u.ppm",frame);FILE*f=fopen((output+suffix).c_str(),"wb");if(f){const unsigned width=rt.SurfaceWidth();fprintf(f,"P6\n%u 240\n255\n",width);for(unsigned i=0;i<width*240;++i){auto p=image[i];unsigned char c[]={uint8_t((p>>11)*255/31),uint8_t(((p>>5)&63)*255/63),uint8_t((p&31)*255/31)};fwrite(c,1,3,f);}fclose(f);}}
 });
 int result=rt.Run(G(bin.entry_point),limit);if(touchReplayFailed)result=1;
 if(result){FILE*f=fopen((output+"/fault.json").c_str(),"wb");if(f){fprintf(f,"{\"registers\":[");for(int i=0;i<17;++i){uint32_t value=0;cpu->RegRead(i,&value);fprintf(f,"%s%u",i?",":"",value);}uint32_t pc=0;cpu->RegRead(Cpu::REG_PC,&pc);uint8_t code[16]{};cpu->MemRead(pc,code,sizeof(code));fprintf(f,"],\"instruction_bytes\":\"");for(auto v:code)fprintf(f,"%02x",v);fprintf(f,"\"}\n");fclose(f);}}
if(!result&&limit&&rt.Frames()!=limit)result=2;
 if(!result&&getenv("RE_STREAM_TEST")){try{rt.PrepareStreamChecks();CheckHybridStream(cpu.get(),rt,bin,output);}catch(const std::exception& e){fprintf(stderr,"[StreamCheck] FAIL %s\n",e.what());result=1;}}
 diagnosticAudio.Close();
 fprintf(stderr,"[HybridResult] result=%d frames=%u failed=%d\n",result,rt.Frames(),rt.Failed());return result;
}
