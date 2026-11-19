#pragma once
#include <array>
#include <cstdint>
#include <cstdio>
#include <vector>
#include <string>
#include <cstring>
struct TouchKeypadButton {uint16_t x,y,w,h,key,index;};
static_assert(sizeof(TouchKeypadButton)==12,"keypad asset rectangle layout");
class TouchKeypad {
public:
 std::array<TouchKeypadButton,12> buttons{};
 std::vector<uint16_t> background,unpressed,pressed;
 bool Load(const std::string& path){
  FILE* f=std::fopen(path.c_str(),"rb");if(!f)return false;
  uint32_t header[6]{};bool ok=std::fread(header,4,6,f)==6&&header[0]==0x504b4552&&header[1]==1&&header[2]==320&&header[3]==240&&header[4]==12;
  if(ok)ok=std::fread(buttons.data(),sizeof(TouchKeypadButton),12,f)==12;
  for(unsigned i=0;ok&&i<12;++i){auto& b=buttons[i];ok=b.w==80&&b.h==40&&b.x+b.w<=320&&b.y+b.h<=240&&b.index==i;}
  if(ok){background.resize(320*240);unpressed.resize(12*80*40);pressed.resize(12*80*40);ok=std::fread(background.data(),2,background.size(),f)==background.size()&&std::fread(unpressed.data(),2,unpressed.size(),f)==unpressed.size()&&std::fread(pressed.data(),2,pressed.size(),f)==pressed.size()&&std::fgetc(f)==EOF;}
  std::fclose(f);loaded=ok;return ok;
 }
 bool Ready()const{return loaded;}
 int Hit(int x,int y)const{
  for(int i=0;i<12;++i){const auto& b=buttons[i];if(x>=b.x&&x<b.x+b.w&&y>=b.y&&y<b.y+b.h)return i;}
  if(y>=0&&y<22&&x>=0&&x<40)return 12;
  if(y>=0&&y<22&&x>=280&&x<320)return 13;
  return -1;
 }
 // Returns a key only on a new touch. Holding or dragging never repeats digits.
 int Update(bool active,bool down,int x,int y){
  int key=-1;int hit=Hit(x,y);
  if(active&&loaded&&down&&!previousDown){latched=hit;if(hit>=0)key=hit<12?buttons[hit].key:hit==12?208:210;}
  if(!active||!down)latched=-1;
  visual=active&&down&&hit==latched&&latched<12?latched:-1;previousDown=down;return key;
 }
 int PressedButton()const{return visual;}
 void Draw(uint16_t* framebuffer)const{
  // Bottom-screen RGB565, rotated column-major storage required by libctru.
  for(int y=0;y<240;++y)for(int x=0;x<320;++x)framebuffer[x*240+239-y]=background[y*320+x];
  for(int i=0;i<12;++i){const auto& b=buttons[i];const auto& pixels=i==visual?pressed:unpressed;const uint16_t* data=pixels.data()+i*80*40;
   for(unsigned y=0;y<b.h;++y)for(unsigned x=0;x<b.w;++x)framebuffer[(b.x+x)*240+239-(b.y+y)]=data[y*b.w+x];}
 }
private:
 bool loaded=false,previousDown=false;int latched=-1,visual=-1;
};
