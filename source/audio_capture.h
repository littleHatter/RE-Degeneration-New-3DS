#pragma once
#include <cstdint>
#include <cstdio>
#include <algorithm>
#include <stdexcept>
#include <array>
class AudioCapture {
 FILE* file=nullptr;uint32_t rate=0;uint64_t samples=0,nonzero=0;int peak=0;std::array<uint64_t,4> phaseSamples{},phaseNonzero{};std::array<int,4> phasePeak{};
 static void put32(unsigned char*p,uint32_t n){for(int i=0;i<4;++i)p[i]=uint8_t(n>>(i*8));}
public:
 void Open(const char* path){file=std::fopen(path,"wb+");if(!file)throw std::runtime_error("Cannot open diagnostic WAV");unsigned char h[44]{};std::fwrite(h,1,44,file);}
 bool Enabled()const{return file!=nullptr;}
 void Write(const int16_t* data,size_t count,uint32_t sampleRate,uint32_t frame){if(!file)return;if(rate&&rate!=sampleRate)throw std::runtime_error("Diagnostic sample rate changed");rate=sampleRate;unsigned phase=frame<600?0:frame<1000?1:frame<1300?2:3;phaseSamples[phase]+=count;for(size_t i=0;i<count;++i){phaseNonzero[phase]+=data[i]!=0;phasePeak[phase]=std::max(phasePeak[phase],data[i]<0?-int(data[i]):int(data[i]));nonzero+=data[i]!=0;peak=std::max(peak,data[i]<0?-int(data[i]):int(data[i]));}if(std::fwrite(data,sizeof(int16_t),count,file)!=count)throw std::runtime_error("Diagnostic WAV write failed");samples+=count;}
 void Close(){if(!file)return;unsigned char h[44]={'R','I','F','F',0,0,0,0,'W','A','V','E','f','m','t',' ',16,0,0,0,1,0,1,0};put32(h+4,uint32_t(36+samples*2));put32(h+24,rate);put32(h+28,rate*2);h[32]=2;h[34]=16;h[36]='d';h[37]='a';h[38]='t';h[39]='a';put32(h+40,uint32_t(samples*2));std::fseek(file,0,SEEK_SET);std::fwrite(h,1,44,file);std::fclose(file);file=nullptr;for(unsigned i=0;i<4;++i)std::fprintf(stderr,"[AudioCapturePhase] phase=%u samples=%llu nonzero=%llu peak=%d\n",i,(unsigned long long)phaseSamples[i],(unsigned long long)phaseNonzero[i],phasePeak[i]);std::fprintf(stderr,"[AudioCapture] samples=%llu nonzero=%llu peak=%d rate=%u\n",(unsigned long long)samples,(unsigned long long)nonzero,peak,rate);}
 ~AudioCapture(){Close();}
};
