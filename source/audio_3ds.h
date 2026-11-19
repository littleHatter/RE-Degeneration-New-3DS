#pragma once
#include <3ds.h>
#include <cstdio>
#include <cstring>
class Audio3DS {
    static constexpr unsigned COUNT=12,SAMPLES=512;
    ndspWaveBuf buffers[COUNT]{};s16* pcm=nullptr;unsigned next=0,queued=0,dropped=0;bool ready=false,playing=false;
public:
    bool Init(){
        next=queued=dropped=0;playing=false;memset(buffers,0,sizeof(buffers));
        Result rc=ndspInit();if(R_FAILED(rc)){printf("[Audio3DS] NDSP init failed: %08lx; continuing without output\n",(unsigned long)rc);return false;}
        pcm=(s16*)linearAlloc(COUNT*SAMPLES*2);
        if(!pcm){puts("[Audio3DS] PCM allocation failed");ndspExit();return false;}
        ready=true;ndspChnReset(0);ndspChnSetInterp(0,NDSP_INTERP_LINEAR);ndspChnSetFormat(0,NDSP_FORMAT_MONO_PCM16);ndspChnSetRate(0,22050.0f);
        float mix[12]{};mix[0]=mix[1]=1.0f;ndspChnSetMix(0,mix);ndspChnSetPaused(0,true);
        for(unsigned i=0;i<COUNT;++i)buffers[i].data_pcm16=pcm+i*SAMPLES;
        puts("[Audio3DS] NDSP ready: 22050 Hz mono");return true;
    }
    void Push(const int16_t* samples,size_t count,uint32_t rate){
        if(!ready)return;
        if(count>SAMPLES||rate!=22050){if(!dropped++)puts("[Audio3DS] Unexpected PCM format");return;}
        auto& b=buffers[next];
        if(b.status==NDSP_WBUF_QUEUED||b.status==NDSP_WBUF_PLAYING){if(++dropped==1||dropped%100==0)printf("[Audio3DS] Queue full; dropped blocks=%u\n",dropped);return;}
        for(size_t i=0;i<count;++i)b.data_pcm16[i]=samples[i];DSP_FlushDataCache(b.data_pcm16,count*2);b.nsamples=count;b.offset=0;b.looping=false;b.status=NDSP_WBUF_FREE;b.next=nullptr;
        ndspChnWaveBufAdd(0,&b);next=(next+1)%COUNT;++queued;
        if(!playing&&queued>=2){ndspChnSetPaused(0,false);playing=true;}
    }
    void Shutdown(){if(ready){ndspChnWaveBufClear(0);ndspChnReset(0);ndspExit();linearFree(pcm);pcm=nullptr;ready=false;}playing=false;}
    ~Audio3DS(){Shutdown();}

};
