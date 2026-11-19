#pragma once
#include <vector>
#include <cstdint>
#include <cstdio>
#include <string>
class BottomScreen {
 std::vector<uint16_t> pixels,loading;unsigned loadingW=0,loadingH=0;
public:
 bool Load(const std::string& path){
  FILE* f=fopen(path.c_str(),"rb");if(!f)return false;uint32_t h[2]{};
  bool ok=fread(h,4,2,f)==2&&h[0]==0x49554552&&h[1]==1;
  pixels.resize(320*240+17*(83*2+77*2+99+61*2));
  ok=ok&&fread(pixels.data(),2,pixels.size(),f)==pixels.size()&&fgetc(f)==EOF;fclose(f);if(!ok)pixels.clear();return ok;
 }
 bool LoadLoading(const std::string& path){
  FILE* f=fopen(path.c_str(),"rb");if(!f)return false;uint32_t h[4]{};bool ok=fread(h,4,4,f)==4&&h[0]==0x444c4552&&h[1]==1&&h[2]>0&&h[2]<=320&&h[3]>0&&h[3]<=240;
  if(ok){loadingW=h[2];loadingH=h[3];loading.resize(loadingW*loadingH);ok=fread(loading.data(),2,loading.size(),f)==loading.size()&&fgetc(f)==EOF;}fclose(f);if(!ok){loading.clear();loadingW=loadingH=0;}return ok;
 }
 void DrawLoading(uint16_t* fb)const{for(unsigned y=0;y<loadingH;++y)for(unsigned x=0;x<loadingW;++x)fb[(320-loadingW+x)*240+239-(240-loadingH+y)]=loading[y*loadingW+x];}
 bool Ready()const{return !pixels.empty();}
 void Draw(uint16_t* fb,uint32_t prompts)const{
  if(!Ready())return;
  for(unsigned y=0;y<240;++y)for(unsigned x=0;x<320;++x)fb[x*240+239-y]=pixels[y*320+x];
  auto blit=[&](unsigned x,unsigned w,unsigned offset){for(unsigned y=0;y<17;++y)for(unsigned dx=0;dx<w;++dx)fb[(x+dx)*240+239-y]=pixels[offset+y*w+dx];};
  unsigned offset=320*240;
  if(prompts&1)blit(0,83,offset);offset+=83*17;
  if(prompts&2)blit(0,83,offset);offset+=83*17;
  if(prompts&4)blit(83,77,offset);offset+=77*17;
  if(prompts&8)blit(83,77,offset);offset+=77*17;
  if(prompts&16)blit(160,99,offset);offset+=99*17;
  if(prompts&32)blit(259,61,offset);offset+=61*17;
  if(prompts&64)blit(259,61,offset);
 }
};
