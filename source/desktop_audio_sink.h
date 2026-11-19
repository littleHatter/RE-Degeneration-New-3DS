#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#ifdef __linux__
#include <dlfcn.h>
#endif

// Optional SDL2 queued-audio output. The diagnostic always captures PCM too.
// ABI: https://wiki.libsdl.org/SDL2/SDL_AudioSpec
class DesktopAudioSink {
public:
    void Push(const int16_t* samples,size_t count,uint32_t rate){
        if(!std::getenv("NFS_LIVE_AUDIO"))return;
#ifdef __linux__
        if(!attempted){attempted=true;Open(rate);}
        if(!device)return;
        if(queued(device)>rate*2){++dropped;return;}
        if(queue(device,samples,static_cast<uint32_t>(count*2))<0){std::fprintf(stderr,"[Desktop audio] Queue failed: %s\n",error());return;}
        submitted+=count;
#endif
    }
    ~DesktopAudioSink(){
#ifdef __linux__
        if(device){std::fprintf(stdout,"[Desktop audio] Submitted %llu samples; dropped %llu blocks\n",(unsigned long long)submitted,(unsigned long long)dropped);close(device);}
        if(initialized)quit(0x10);
        if(lib)dlclose(lib);
#endif
    }
private:
#ifdef __linux__
    struct Spec {int freq;uint16_t format;uint8_t channels,silence;uint16_t samples,padding;uint32_t size;void(*callback)(void*,uint8_t*,int);void* userdata;};
    void* lib=nullptr;uint32_t device=0;bool attempted=false,initialized=false;uint64_t submitted=0,dropped=0;
    int(*init)(uint32_t)=nullptr;void(*quit)(uint32_t)=nullptr;const char*(*error)()=nullptr;
    uint32_t(*open)(const char*,int,const Spec*,Spec*,int)=nullptr;
    void(*close)(uint32_t)=nullptr;void(*pause)(uint32_t,int)=nullptr;
    int(*queue)(uint32_t,const void*,uint32_t)=nullptr;uint32_t(*queued)(uint32_t)=nullptr;
    template<class T> bool Load(T& fn,const char* name){fn=reinterpret_cast<T>(dlsym(lib,name));return fn!=nullptr;}
    void Open(uint32_t rate){
        lib=dlopen("libSDL2-2.0.so.0",RTLD_NOW|RTLD_LOCAL);
        if(!lib){std::fprintf(stderr,"[Desktop audio] SDL2 unavailable; PCM capture continues\n");return;}
        if(!Load(init,"SDL_InitSubSystem")||!Load(quit,"SDL_QuitSubSystem")||!Load(error,"SDL_GetError")||!Load(open,"SDL_OpenAudioDevice")||!Load(close,"SDL_CloseAudioDevice")||!Load(pause,"SDL_PauseAudioDevice")||!Load(queue,"SDL_QueueAudio")||!Load(queued,"SDL_GetQueuedAudioSize")){std::fprintf(stderr,"[Desktop audio] SDL2 API unavailable\n");return;}
        if(init(0x10)<0){std::fprintf(stderr,"[Desktop audio] Init failed: %s\n",error());return;}
        initialized=true;Spec desired{};desired.freq=static_cast<int>(rate);desired.format=0x8010;desired.channels=1;desired.samples=512;
        device=open(nullptr,0,&desired,nullptr,0);
        if(!device){std::fprintf(stderr,"[Desktop audio] Open failed: %s\n",error());return;}
        pause(device,0);std::fprintf(stdout,"[Desktop audio] SDL2 output active: %u Hz mono s16le\n",rate);
    }
#endif
};
