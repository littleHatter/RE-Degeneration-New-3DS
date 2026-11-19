#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <algorithm>
#ifdef __linux__
#include <dlfcn.h>
#elif defined(__3DS__)
#include <mpg123.h>
#endif
// MP3 decode: dynamic libmpg123 on Linux, statically linked portlib on 3DS.
class DesktopMp3 {
public:
    DesktopMp3()=default;
    DesktopMp3(const DesktopMp3&)=delete;
    DesktopMp3& operator=(const DesktopMp3&)=delete;
    ~DesktopMp3(){
#ifdef __linux__
        if(library){if(shutdown)shutdown();dlclose(library);}
#elif defined(__3DS__)
        if(attempted&&shutdown)shutdown();
#endif
    }
    bool Available(){
#ifdef __linux__
        if(attempted)return library!=nullptr;attempted=true;
        library=dlopen("libmpg123.so.0",RTLD_NOW|RTLD_LOCAL);if(!library)return false;
#define LOAD(field,symbol) field=reinterpret_cast<decltype(field)>(dlsym(library,symbol));if(!field){dlclose(library);library=nullptr;return false;}
        LOAD(init,"mpg123_init") LOAD(shutdown,"mpg123_exit") LOAD(create,"mpg123_new") LOAD(destroy,"mpg123_delete")
        LOAD(openFeed,"mpg123_open_feed") LOAD(feed,"mpg123_feed") LOAD(read,"mpg123_read") LOAD(format,"mpg123_getformat")
#undef LOAD
        if(init()!=0){dlclose(library);library=nullptr;return false;}return true;
#elif defined(__3DS__)
        if(attempted)return library!=nullptr;attempted=true;
#define STATIC_LOAD(field,symbol) field=reinterpret_cast<decltype(field)>(&symbol)
        STATIC_LOAD(init,mpg123_init);STATIC_LOAD(shutdown,mpg123_exit);
        STATIC_LOAD(create,mpg123_new);STATIC_LOAD(destroy,mpg123_delete);
        STATIC_LOAD(openFeed,mpg123_open_feed);STATIC_LOAD(feed,mpg123_feed);
        STATIC_LOAD(read,mpg123_read);STATIC_LOAD(format,mpg123_getformat);
#undef STATIC_LOAD
        if(init()!=0)return false;library=this;return true;
#else
        return false;
#endif
    }
    bool Decode(const std::vector<uint8_t>& input,std::vector<int16_t>& mono,std::string& error){
#if defined(__linux__) || defined(__3DS__)
        if(!Available()){error="libmpg123.so.0 is unavailable";return false;}
        void* h=create(nullptr,nullptr);if(!h){error="mpg123_new failed";return false;}
        if(openFeed(h)||feed(h,input.data(),input.size())){destroy(h);error="MP3 input rejected";return false;}
        std::vector<uint8_t> raw;long rate=0;int channels=0,encoding=0;bool valid=false;int rc=0;
        for(unsigned count=0;count<100000;++count){
            uint8_t block[8192];size_t got=0;rc=read(h,block,sizeof(block),&got);
            if(rc==-11){if(format(h,&rate,&channels,&encoding)||rate<8000||rate>96000||(channels!=1&&channels!=2)||encoding!=0xd0){error="Unsupported decoded PCM format";valid=false;break;}valid=true;}
            raw.insert(raw.end(),block,block+got);
            if(raw.size()>128u*1024*1024){error="Decoded MP3 exceeds size limit";valid=false;break;}
            if(rc==0||rc==-11)continue;
            if(rc!=-10&&rc!=-12){error="MP3 decoding failed ("+std::to_string(rc)+")";valid=false;}
            break;
        }
        destroy(h);if(!valid||raw.empty()){if(error.empty())error="No MP3 audio frames";return false;}
        size_t frames=raw.size()/(2*channels);size_t length=uint64_t(frames)*22050/rate;mono.resize(length);
        auto sample=[&](size_t index){int32_t sum=0;for(int c=0;c<channels;++c){int16_t v=0;std::memcpy(&v,raw.data()+(index*channels+c)*2,2);sum+=v;}return sum/channels;};
        for(size_t i=0;i<length;++i){uint64_t at=uint64_t(i)*rate;size_t a=at/22050;uint32_t fraction=at%22050;size_t b=std::min(a+1,frames-1);mono[i]=int16_t((int64_t(sample(a))*(22050-fraction)+int64_t(sample(b))*fraction)/22050);}
        return true;
#else
        error="Desktop MP3 decoder is unavailable on this platform";return false;
#endif
    }
private:
    bool attempted=false;void* library=nullptr;
    void(*shutdown)()=nullptr;int(*init)()=nullptr;void*(*create)(const char*,int*)=nullptr;void(*destroy)(void*)=nullptr;
    int(*openFeed)(void*)=nullptr;int(*feed)(void*,const unsigned char*,size_t)=nullptr;
    int(*read)(void*,unsigned char*,size_t,size_t*)=nullptr;int(*format)(void*,long*,int*,int*)=nullptr;
};
