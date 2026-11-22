#include "gles.h"
#include "assetviewer.h"
#include "custommodel.h"
#include "textures.h"
#include <cstdio>
#ifdef __3DS__
#include "gl3ds.h"
void InstallProbeHost(){
    GLES::SetHost({GL3DS::Init,GL3DS::Proc,[](int& w,int& h){w=400;h=240;},GL3DS::EndFrame});
}
#else
extern "C" {
void* eglGetDisplay(void*);
unsigned eglInitialize(void*,int*,int*);
unsigned eglBindAPI(unsigned);
unsigned eglChooseConfig(void*,const int*,void**,int,int*);
void* eglCreatePbufferSurface(void*,void*,const int*);
void* eglCreateContext(void*,void*,void*,const int*);
unsigned eglMakeCurrent(void*,void*,void*,void*);
void* eglGetProcAddress(const char*);
}
void InstallProbeHost(){
    GLES::SetHost({[]{
        auto* display=eglGetDisplay(nullptr);
        if(!display||!eglInitialize(display,nullptr,nullptr)||!eglBindAPI(0x30a2))return false;
        constexpr int config[]={0x3033,1,0x3040,8,0x3024,8,0x3023,8,0x3022,8,0x3038};
        constexpr int dimensions[]={0x3057,320,0x3056,240,0x3038};
        constexpr int defaults[]={0x3038};
        void* chosen=nullptr;
        int count=0;
        if(!eglChooseConfig(display,config,&chosen,1,&count)||!count)return false;
        auto* surface=eglCreatePbufferSurface(display,chosen,dimensions);
        auto* context=eglCreateContext(display,chosen,nullptr,defaults);
        const bool ok=surface&&context&&eglMakeCurrent(display,surface,surface,context);
        std::fprintf(stderr,"[HardwareProbe] Mesa compatibility context: %s\n",ok?"ready":"failed");
        return ok;
    },eglGetProcAddress,{},{}});
}
#endif
namespace AssetViewer {
bool Recording(){return false;}
void OnTexImage(uint32_t,int,int,const char*,uint32_t,bool){}
void OnDeleteTexture(uint32_t){}
void AddDraw(const DrawIn&){}
void OnPresentBegin(){}
void OnPresentEnd(){}
}
namespace CustomModel {
bool Covers(){return false;}
void Draw(const float*){}
void NoteTexture(uint32_t,const std::string&){}
void ForgetTexture(uint32_t){}
}
namespace TexturePack {
bool Replacement(uint32_t,std::vector<uint32_t>&,int&,int&){return false;}
std::string OriginalPath(uint32_t){return {};}
}
