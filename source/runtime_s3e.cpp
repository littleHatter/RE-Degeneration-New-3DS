#include "gles.h"
void InstallProbeHost();
#include "runtime_s3e.h"
#include "resident_ui.h"
#include "hybrid_trace.h"
#include "loader.h"
#include "heap.h"
#include "asset_read.h"
#include "save_store.h"
#include "third_party/lzma/LzmaDec.h"
#include <algorithm>
#include "runtime_clock.h"
#include "timer_queue.h"
#include "desktop_mp3.h"
#include "pcm_volume.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <filesystem>
#include <map>
#include <deque>
#include <set>
#include <vector>
#include <cctype>
#include <zlib.h>

namespace {
using U=uint32_t;using R=std::array<U,4>;using Done=std::function<void(U)>;
std::string lower(std::string s){for(char& c:s)c=static_cast<char>(std::tolower(static_cast<unsigned char>(c)));return s;}
std::string trim(std::string s){auto a=s.find_first_not_of(" \t\r\n");if(a==std::string::npos)return {};return s.substr(a,s.find_last_not_of(" \t\r\n")-a+1);}
void* LAlloc(ISzAllocPtr,size_t n){return std::malloc(n);}void LFree(ISzAllocPtr,void* p){std::free(p);}const ISzAlloc kLzmaAlloc={LAlloc,LFree};
}
struct S3ERuntime::Impl {
    HybridTrace hybrid;
    ResidentUi consoleUi;
    struct ResRequest {U group,name,out,lr;};std::map<U,ResRequest> resourceRequests;
    struct ResEvent {U frame,group,name,caller,result;};std::deque<ResEvent> recentResources;
    std::deque<std::string> recentFiles;
    void resourceContext(){
        fprintf(stderr,"[ResourceContext] frame=%u recentLookups=%zu recentFiles=%zu largestFree=%u\n",frames,recentResources.size(),recentFiles.size(),heap.LargestFree());
        for(const auto& e:recentResources)fprintf(stderr,"[ResourceHistory] frame=%u group=%08x name=%08x caller=%08x result=%08x\n",e.frame,e.group,e.name,e.caller,e.result);
        for(const auto& e:recentFiles)fprintf(stderr,"[FileHistory] %s\n",e.c_str());
        fflush(stdout);fflush(stderr);
    }
    void recordFile(const std::string& path,U h,U caller){if(!getenv("RE_RESOURCE_TRACE"))return;char b[128];snprintf(b,sizeof(b),"frame=%u handle=%08x caller=%08x path=",frames,h,caller);recentFiles.push_back(std::string(b)+path);if(recentFiles.size()>24)recentFiles.pop_front();fprintf(stderr,"[FileResult] %s\n",recentFiles.back().c_str());fflush(stderr);}

    Cpu* cpu;std::string assets,saves,raceCity;GuestHeap heap;std::vector<std::string> imports;
    S3ERuntime::VideoPlayer videoPlayer;U videoVolume=256;bool videoPlaying=false,videoPending=false;std::string videoPath;S3ERuntime::VideoRequest videoRequest{};
    DesktopMp3 mp3;
    struct Music {std::vector<int16_t> samples;size_t pos=0;U repeats=0,volume=256;bool playing=false,paused=false;};Music music;U audioError=0;
    std::map<std::string,std::vector<int16_t>> musicCache;
    U secureError=0;bool soundAllPaused=false;
    std::map<U,U> memoryHeaps;
    std::map<U,std::string> logicalNames;
    std::map<U,uint64_t> logicalPosition;
    struct ReadStats {std::string name;uint64_t calls=0,bytes=0,minOffset=UINT64_MAX,maxEnd=0;uLong crc=0;};
    std::map<U,ReadStats> logicalStats;
    std::map<std::string,unsigned> hostReadCounts;
    std::map<std::string,std::string> config;std::array<U,3> memmgr{};
    struct File{std::string name;std::vector<uint8_t> data;size_t pos=0;U backing=0;};std::map<U,File> files;
    struct Directory {std::vector<std::string> names;size_t next=0;};std::map<U,Directory> directories;
    std::vector<std::array<U,11>> fs;std::set<size_t> activeFS;std::map<U,size_t> handles;
    bool keypadOpen=false;U keypadObject=0;std::deque<U> keypadKeys;bool keypadPulseRelease=false;
    TimerQueue timers;bool timerDispatch=false;
    struct Regs{std::array<U,17> v;};struct Task{Regs regs;Done done;};std::vector<Task> tasks;
    struct Decoder {
        CLzmaDec dec{};bool ready=false;U reader=0,user=0,request=0,buffer=0;uint64_t remaining=0;
        std::vector<uint8_t> in;size_t pos=0;
        Decoder(){LzmaDec_Construct(&dec);}~Decoder(){if(ready)LzmaDec_Free(&dec,&kLzmaAlloc);}
    };std::map<U,std::shared_ptr<Decoder>> decoders;
    std::map<U,std::pair<U,U>> keyCallbacks,deviceCallbacks,pointerCallbacks,videoCallbacks;
    static constexpr U soundRate=22050,soundBlock=512,soundChannels=16;
    struct Channel {bool playing=false,paused=false;U rate=8000,volume=256,uservar=0,start=0,length=0;int32_t repeat=1,loop=0;U generation=0;double pos=0;std::array<U,4> fn{},ud{};};
    std::array<Channel,soundChannels> channels{};U masterVolume=256,mixBuf=0,genInfo=0,endInfo=0;bool mixing=false;uint64_t audioSamples=0;U audioStart=0;bool audioStarted=false;
    std::function<void(const int16_t*,size_t,U)> audioOut;
    std::function<void(int16_t*,size_t,U,bool)> externalMusic;
    std::function<void(U,const int16_t*,size_t,U)> audioStemOut;
    std::array<std::vector<int16_t>,soundChannels> audioStems;
    uint64_t audioWritten=0;
    bool traceAudio=std::getenv("NFS_AUDIO_TRACE")!=nullptr;
    std::array<int32_t,soundBlock> mixAccumulator{};
    std::array<int16_t,soundBlock> outputBlock{},channelScratch{},musicStemBlock{},effectsStemBlock{};
    U soundStarts=0,fileApiOpens=0,hostReads=0,mixBlocks=0,generatorCalls=0,maxGeneratorMs=0,maxMixMs=0,mixBegin=0;
    struct Gap{U frame=0,ms=0,starts=0,opens=0;};std::array<Gap,8> worstGaps{};
    U lastFrameTime=0,lastFrameStarts=0,lastFrameOpens=0;
    void measureFrame(){U now=ms();if(lastFrameTime){Gap g{frames,U(now-lastFrameTime),U(soundStarts-lastFrameStarts),U(fileApiOpens-lastFrameOpens)};if(g.ms>worstGaps.back().ms){worstGaps.back()=g;std::sort(worstGaps.begin(),worstGaps.end(),[](const Gap&a,const Gap&b){return a.ms>b.ms;});}}lastFrameTime=now;lastFrameStarts=soundStarts;lastFrameOpens=fileApiOpens;}
    void reportPerformance(){if(getenv("PAN_FILE_TRACE"))for(const auto& pair:logicalStats){const auto& st=pair.second;if(st.calls)fprintf(stderr,"[LogicalSummary] name=%s handle=%08x calls=%llu bytes=%llu min=%llu maxEnd=%llu crc32=%08lx\n",st.name.c_str(),pair.first,(unsigned long long)st.calls,(unsigned long long)st.bytes,(unsigned long long)st.minOffset,(unsigned long long)st.maxEnd,(unsigned long)st.crc);}std::fprintf(stdout,"[Perf] soundStarts=%u fileOpens=%u hostReads=%u mixBlocks=%u generatorCalls=%u maxGeneratorMs=%u maxMixMs=%u\n",soundStarts,fileApiOpens,hostReads,mixBlocks,generatorCalls,maxGeneratorMs,maxMixMs);for(const auto&g:worstGaps)if(g.frame)std::fprintf(stdout,"[PerfGap] frame=%u gapMs=%u soundStarts=%u fileOpens=%u\n",g.frame,g.ms,g.starts,g.opens);}

    void audioEvent(const char* event,U ch){if(!traceAudio)return;std::fprintf(stdout,"[AudioEvent] record=%.6f frame=%u ms=%u event=%s ch=%u generator=%08x\n",double(audioWritten)/soundRate,frames,ms(),event,ch,ch<soundChannels?channels[ch].fn[1]:0);}


    std::array<U,256> keyState{};Keys desired{};
    std::function<void(U,const uint16_t*,Keys&)> present;
#ifdef __3DS__
    static constexpr bool periodicLogging=false;
#else
    static constexpr bool periodicLogging=true;
#endif
    uint64_t start=NfsClockMs();U lastPoll=0,lastHeartbeat=0,pollCounter=0;
    std::function<void(Keys&)> poll;
    std::set<std::string> seen;bool quit=false,failed=false;U frames=0,limit=0;uint64_t calls=0;
    explicit Impl(Cpu* c,std::string a,std::string s):cpu(c),assets(std::move(a)),saves(std::move(s)),consoleUi(c){heap.Init(HEAP_BASE+256,HEAP_SIZE-256);if(getenv("PGR_STATE_LIFETIME"))heap.SetObserver([this](const char* action,U base,U size){U state=0;cpu->MemRead(G(0x4a0c4154),&state,4);if(state&&uint64_t(base)<=uint64_t(state)+0x74&&uint64_t(base)+size>state){U pc=0;cpu->RegRead(Cpu::REG_PC,&pc);fprintf(stderr,"[StateLifetime] event=%s base=%08x bytes=%u state=%08x pc=%08x lr=%08x\n",action,base,size,state,pc,reg(Cpu::REG_LR));}});std::error_code ec;std::filesystem::create_directories(saves,ec);}
    void fatal(const std::string& msg){if(!failed){std::fprintf(stderr,"[S3E] ERROR: %s\n",msg.c_str());std::fprintf(stderr,"[FaultState] pc=%08x lr=%08x sp=%08x r0=%08x r1=%08x r2=%08x r3=%08x callbacks=%zu\n",reg(15),reg(14),reg(13),reg(0),reg(1),reg(2),reg(3),tasks.size());}failed=quit=true;cpu->Stop();}
    U reg(int n){U x=0;cpu->RegRead(n,&x);return x;}
    void set(int n,U x){cpu->RegWrite(n,&x);}
    void rd(U a,void* dst,size_t n){if(n&&cpu->MemRead(a,dst,n)!=Cpu::OK){std::memset(dst,0,n);fatal("unmapped read "+std::to_string(a));}}
    void wr(U a,const void* src,size_t n){
        if(getenv("PGR_HOST_WRITE_TRACE")&&n){U state=0;cpu->MemRead(G(0x4a0c4154),&state,4);if(state>=HEAP_BASE&&state<HEAP_BASE+HEAP_SIZE&&uint64_t(a)<uint64_t(state)+32&&uint64_t(a)+n>state){U before[8]{};cpu->MemRead(state,before,32);fprintf(stderr,"[HostStateWrite] address=%08x bytes=%zu state=%08x sizeOf=%u lr=%08x before=%08x,%08x,%08x,%08x\n",a,n,state,heap.SizeOf(state),reg(Cpu::REG_LR),before[0],before[1],before[2],before[3]);}}
        if(n&&cpu->MemWrite(a,src,n)!=Cpu::OK)fatal("unmapped write "+std::to_string(a));
    }
    U word(U a){U x=0;rd(a,&x,4);return x;}void word(U a,U x){wr(a,&x,4);}
    std::string str(U a,size_t cap=4096){std::string s;if(!a)return s;for(size_t k=0;k<cap;++k){char c=0;rd(a+k,&c,1);if(!c)break;s+=c;}return s;}
    void zero(U a,U n){static const std::array<uint8_t,4096> z{};while(n){U b=std::min<U>(n,z.size());wr(a,z.data(),b);a+=b;n-=b;}}
    U alloc(U n){U a=heap.Alloc(n);if(getenv("NFS_DIAG"))fprintf(stderr,"[Alloc] %u -> %08x lr=%08x\n",n,a,reg(Cpu::REG_LR));if(a)zero(a,heap.SizeOf(a));else std::fprintf(stderr,"[S3E] allocation failed: %lu bytes; largest %lu\n",(unsigned long)n,(unsigned long)heap.LargestFree());return a;}
    U realloc_(U a,U n){if(getenv("NFS_DIAG"))fprintf(stderr,"[Realloc] %08x -> %u lr=%08x\n",a,n,reg(Cpu::REG_LR));U old=heap.SizeOf(a),from=0,count=0;U result=heap.Realloc(a,n,&from,&count);if(result&&from){std::vector<uint8_t> data(count);rd(from,data.data(),count);wr(result,data.data(),count);heap.Free(from);if(heap.SizeOf(result)>count)zero(result+count,heap.SizeOf(result)-count);}else if(result&&heap.SizeOf(result)>old)zero(result+old,heap.SizeOf(result)-old);return result;}
    void pc(U target){U flags=reg(Cpu::REG_CPSR);flags=(flags&~32u)|((target&1)?32u:0);set(Cpu::REG_CPSR,flags);set(Cpu::REG_PC,target);}
    void finish(U v){set(Cpu::REG_R0,v);pc(reg(Cpu::REG_LR));}
    Regs save(){Regs s;for(int k=0;k<17;++k)s.v[k]=reg(k);return s;}
    void restore(const Regs& s){for(int k=0;k<15;++k)set(k,s.v[k]);set(Cpu::REG_CPSR,s.v[16]);set(Cpu::REG_PC,s.v[15]|((s.v[16]&32)?1:0));}
    void call(U fn,std::vector<U> a,Done done){if(!fn){done(0);return;}tasks.push_back({save(),std::move(done)});U sp=reg(Cpu::REG_SP)-32;set(Cpu::REG_SP,sp);for(size_t k=0;k<a.size();++k){if(k<4)set(k,a[k]);else word(sp+4*(k-4),a[k]);}set(Cpu::REG_LR,TRAMPOLINE_BASE+imports.size()*8);pc(fn);}
    void timerStep(uint64_t now,uint64_t generation,Done done){
        TimerQueue::Event event;
        if(!timers.TakeDue(now,generation,event)){timerDispatch=false;done(0);return;}
        fprintf(stderr,"[TimerFire] frame=%lu id=%llu due=%llu now=%llu callback=%08lx user=%08lx\n",(unsigned long)frames,(unsigned long long)event.id,(unsigned long long)event.due,(unsigned long long)now,(unsigned long)event.callback,(unsigned long)event.user);
        call(event.callback,{0,event.user},[this,now,generation,done](U){timerStep(now,generation,done);});
    }
    void pumpTimers(Done done){if(timerDispatch){done(0);return;}timerDispatch=true;timerStep(NfsClockMs()-start,timers.Generation(),std::move(done));}
    void returned(){if(tasks.empty()){fatal("orphan callback return");return;}U result=reg(Cpu::REG_R0);Task t=std::move(tasks.back());tasks.pop_back();restore(t.regs);t.done(result);}
    std::string norm(std::string p){std::replace(p.begin(),p.end(),'\\','/');p=lower(p);for(auto pre:{"rom:/","raw:/","ram:/","data:/"})if(p.rfind(pre,0)==0){p=p.substr(std::strlen(pre));break;}while(!p.empty()&&p[0]=='/')p.erase(p.begin());for(size_t at;(at=p.find("//"))!=std::string::npos;)p.erase(at,1);return p;}
    unsigned fileTraceCount=0;
    void fileTrace(const char* action,const std::string& name,U handle,uint64_t offset,uint64_t requested,uint64_t actual){if(!getenv("PAN_FILE_TRACE"))return;if(std::strcmp(action,"read")==0&&++hostReadCounts[name]>16&&requested==1&&actual)return;fprintf(stderr,"[FileTrace] action=%s name=%s handle=%08x offset=%llu requested=%llu actual=%llu lr=%08x\n",action,name.c_str(),handle,(unsigned long long)offset,(unsigned long long)requested,(unsigned long long)actual,reg(Cpu::REG_LR));}
    std::string resolveAsset(std::string name){
        if(name.size()==6&&std::isdigit(static_cast<unsigned char>(name[0]))&&std::isdigit(static_cast<unsigned char>(name[1]))&&name.substr(2)==".mp3"){
            std::error_code ec;if(!std::filesystem::exists(assets+"/"+name,ec)){
                std::string alias="mp3_music/"+name;if(std::filesystem::exists(assets+"/"+alias,ec)){fprintf(stderr,"[PathAlias] requested=%s resolved=%s\n",name.c_str(),alias.c_str());return alias;}
            }
        }return name;
    }
    U hostOpen(const std::string& name,const std::string& mode){
        if(mode!="r"&&mode!="rb"&&mode!="rU"&&mode!="rbU")return 0;
        std::string p=norm(name);if(p.find("..")!=std::string::npos)return 0;p=resolveAsset(p);
        File file;file.name=p;
        if(!ReadAssetExact(assets+"/"+p,file.data)){fileTrace("open-miss",p,0,0,0,0);return 0;}
        ++hostReads;
        if(file.data.size()>=(4u<<20))fprintf(stderr,"[HostAsset] exact-size read name=%s bytes=%zu\n",p.c_str(),file.data.size());
        U h=alloc(64);if(!h)return 0;files[h]=std::move(file);
        fileTrace("open",p,h,0,0,files[h].data.size());return h;
    }

    struct Open{R r;size_t next=0;Done done;};
    void openStep(std::shared_ptr<Open> s){while(s->next<fs.size()){size_t n=s->next++;if(activeFS.count(n)||!fs[n][0])continue;activeFS.insert(n);call(fs[n][0],{s->r[0],s->r[1]},[this,s,n](U h){activeFS.erase(n);if(h){handles[h]=n;s->done(h);}else openStep(s);});return;}s->done(hostOpen(str(s->r[0]),str(s->r[1])));}
    void open(R r,Done done){std::string path=norm(str(r[0]));for(const char* city:{"cairo","london","paris","sanfran","shanghai"})if(path.rfind(std::string("tracks/")+city+"/",0)==0)raceCity=std::string(city)=="sanfran"?"sanfrancisco":city;U override=HybridTrace::OverrideAllowed(path)?hostOpen("overrides/"+path,str(r[1])):0;if(override){std::fprintf(stdout,"[Asset override] %s\n",path.c_str());done(override);return;}auto s=std::make_shared<Open>();s->r=r;U name=alloc(path.size()+1);if(!name){done(0);return;}wr(name,path.c_str(),path.size()+1);s->r[0]=name;s->done=[this,name,path,done](U h){heap.Free(name);if(h){logicalNames[h]=path;logicalPosition[h]=0;logicalStats[h]=ReadStats{path};}done(h);};openStep(s);}
    void close(U h,Done done){auto f=files.find(h);if(f!=files.end()){files.erase(f);heap.Free(h);done(0);return;}auto g=handles.find(h);if(g==handles.end()){done(1);return;}size_t n=g->second;handles.erase(g);call(fs[n][5],{h},std::move(done));}
    void read(R r,Done done){if(hybrid.active){auto host=files.find(r[3]);if(host!=files.end())hybrid.Backend(host->second.name,host->second.pos,uint64_t(r[1])*r[2]);}auto g=handles.find(r[3]);if(g!=handles.end()){std::string name=logicalNames[r[3]];uint64_t offset=logicalPosition[r[3]];
            call(fs[g->second][1],{r[0],r[1],r[2],r[3]},[this,r,name,offset,done](U got){
                uint64_t count=uint64_t(got)*r[1];logicalPosition[r[3]]=offset+count;
                if(getenv("PAN_FILE_TRACE")){
                    auto& stats=logicalStats[r[3]];++stats.calls;stats.bytes+=count;stats.minOffset=std::min(stats.minOffset,offset);stats.maxEnd=std::max(stats.maxEnd,offset+count);
                    std::vector<uint8_t> bytes;if(count<=(16u<<20)){bytes.resize(count);rd(r[0],bytes.data(),bytes.size());if(!bytes.empty())stats.crc=crc32(stats.crc,bytes.data(),bytes.size());}
                    if(stats.calls<=16||count!=1)fprintf(stderr,"[LogicalRead] name=%s handle=%08x offset=%llu requested=%llu returned=%llu crc32=%08lx\n",name.c_str(),r[3],(unsigned long long)offset,(unsigned long long)(uint64_t(r[1])*r[2]),(unsigned long long)count,(unsigned long)crc32(0,bytes.data(),bytes.size()));
                }done(got);
            });return;}auto f=files.find(r[3]);if(f==files.end()){done(0);return;}File& file=f->second;size_t n=std::min<uint64_t>(uint64_t(r[1])*r[2],file.pos<file.data.size()?file.data.size()-file.pos:0);fileTrace("read",file.name,r[3],file.pos,uint64_t(r[1])*r[2],n);wr(r[0],file.data.data()+std::min(file.pos,file.data.size()),n);file.pos+=n;done(r[1]?n/r[1]:0);}
    void seek(R r,Done done){auto g=handles.find(r[0]);if(g!=handles.end()){call(fs[g->second][3],{r[0],r[1],r[2]},[this,r,done](U result){if(!result){if(r[2]==0)logicalPosition[r[0]]=r[1];else if(r[2]==1)logicalPosition[r[0]]+=int32_t(r[1]);else logicalPosition[r[0]]=UINT32_MAX;}if(getenv("PAN_FILE_TRACE"))fprintf(stderr,"[LogicalSeek] name=%s handle=%08x offset=%d origin=%u result=%u\n",logicalNames[r[0]].c_str(),r[0],int32_t(r[1]),r[2],result);done(result);});return;}auto f=files.find(r[0]);if(f==files.end()||r[2]>2){done(1);return;}File& file=f->second;int64_t pos=(r[2]==0?0:r[2]==1?file.pos:file.data.size())+int64_t(int32_t(r[1]));if(pos<0){done(1);return;}fileTrace("seek",file.name,r[0],file.pos,uint32_t(r[1]),pos);file.pos=pos;done(0);}
    void tell(U h,Done done){auto g=handles.find(h);if(g!=handles.end()){call(fs[g->second][4],{h},[this,h,done](U position){logicalPosition[h]=position;done(position);});return;}auto f=files.find(h);done(f==files.end()?0:f->second.pos);}
    void getSize(U h,Done done){auto f=files.find(h);if(f!=files.end()){done(f->second.data.size());return;}tell(h,[this,h,done](U old){seek({h,0,2,0},[this,h,old,done](U){tell(h,[this,h,old,done](U n){seek({h,old,0,0},[done,n](U){done(n);});});});});}
    struct LineRead {U dst=0,size=0,handle=0,scratch=0;std::vector<char> text;};
    void lineDone(std::shared_ptr<LineRead> s){U result=s->text.empty()?0:s->dst;s->text.push_back(0);wr(s->dst,s->text.data(),s->text.size());heap.Free(s->scratch);finish(result);}
    void lineStep(std::shared_ptr<LineRead> s){
        if(s->text.size()+1>=s->size){lineDone(s);return;}
        read({s->scratch,1,1,s->handle},[this,s](U got){if(got!=1){lineDone(s);return;}char c=0;rd(s->scratch,&c,1);s->text.push_back(c);if(c=='\n')lineDone(s);else lineStep(s);});
    }
    struct DecompRead{std::shared_ptr<Decoder> d;U dst=0,countptr=0;size_t need=0;std::vector<uint8_t> out;};
    void decompFinish(std::shared_ptr<DecompRead> s,U error=0){hybrid.Decode(s->need,s->out.size(),error,reg(Cpu::REG_PC),reg(Cpu::REG_LR));if(getenv("PAN_FILE_TRACE"))fprintf(stderr,"[Decode] dst=%08x need=%zu produced=%zu remaining=%llu error=%u\n",s->dst,s->need,s->out.size(),(unsigned long long)s->d->remaining,error);if(getenv("NFS_RESOURCE_TRACE")&&s->out.size()>=4&&s->out[0]==0x3d){fprintf(stderr,"[Decomp] dst=%08x size=%zu bytes=",s->dst,s->out.size());for(size_t i=0;i<std::min<size_t>(s->out.size(),256);++i)fprintf(stderr,"%02x",s->out[i]);fprintf(stderr,"\n");}wr(s->dst,s->out.data(),s->out.size());word(s->countptr,s->out.size());finish(error);}
    void decompStep(std::shared_ptr<DecompRead> s){auto d=s->d;
        for(;;){
            if(s->out.size()>=s->need){decompFinish(s);return;}
            if(d->ready&&(s->out.size()>=s->need||d->remaining==0)){decompFinish(s);return;}
            if(d->pos>=d->in.size()){
                word(d->request,d->buffer);word(d->request+4,4096);
                call(d->reader,{d->request,d->user},[this,s,d](U n){if(!n||n>4096){decompFinish(s,1);return;}d->in.resize(n);rd(d->buffer,d->in.data(),n);d->pos=0;decompStep(s);});return;
            }
            if(!d->ready){if(d->in.size()-d->pos<13){decompFinish(s,1);return;}const uint8_t* p=d->in.data()+d->pos;d->remaining=0;for(int k=0;k<8;++k)d->remaining|=uint64_t(p[5+k])<<(8*k);if(LzmaDec_Allocate(&d->dec,p,5,&kLzmaAlloc)!=SZ_OK){decompFinish(s,1);return;}d->ready=true;LzmaDec_Init(&d->dec);d->pos+=13;s->need=std::min<uint64_t>(s->need,d->remaining);}
            size_t prev=s->out.size();SizeT produced=std::min<uint64_t>(s->need-prev,d->remaining);SizeT consumed=d->in.size()-d->pos;s->out.resize(prev+produced);ELzmaStatus status;
            SRes rc=LzmaDec_DecodeToBuf(&d->dec,s->out.data()+prev,&produced,d->in.data()+d->pos,&consumed,LZMA_FINISH_ANY,&status);s->out.resize(prev+produced);d->pos+=consumed;d->remaining-=produced;
            if(rc!=SZ_OK){decompFinish(s,1);return;}if(!produced&&!consumed){decompFinish(s,1);return;}
        }
    }
    void updateKeys(){
        int pulse=-1;
        if(!keypadOpen){keypadKeys.clear();keypadPulseRelease=false;}
        else if(keypadPulseRelease)keypadPulseRelease=false;
        else if(!keypadKeys.empty()){pulse=int(keypadKeys.front());keypadKeys.pop_front();keypadPulseRelease=true;fprintf(stderr,"[KeypadKey] frame=%lu key=%d\n",(unsigned long)frames,pulse);}
        auto changes=std::make_shared<std::vector<std::pair<U,bool>>>();for(U k=0;k<256;++k){bool prev=keyState[k]&1,now=desired[k]||int(k)==pulse;keyState[k]=(now?1u:0u)|(now&&!prev?2u:0u)|(prev&&!now?4u:0u);if(prev!=now)changes->push_back({k,now});}keyStep(changes,0);}
    void keyStep(std::shared_ptr<std::vector<std::pair<U,bool>>> c,size_t at){auto cb=keyCallbacks.find(0);if(at>=c->size()||cb==keyCallbacks.end()){finish(0);return;}U p=alloc(8);word(p,(*c)[at].first);word(p+4,(*c)[at].second);auto fn=cb->second;call(fn.first,{p,fn.second},[this,c,at,p](U){heap.Free(p);keyStep(c,at+1);});}
    bool playMusic(const std::vector<uint8_t>& data,U repeat,const std::string& name){
        std::string error;auto cached=musicCache.find(name);
        if(cached==musicCache.end()){
            std::vector<int16_t> pcm;if(!mp3.Decode(data,pcm,error)){fprintf(stderr,"[MusicError] name=%s error=%s\n",name.c_str(),error.c_str());audioError=1;return false;}
            cached=musicCache.emplace(name,std::move(pcm)).first;
        }
        music.samples=cached->second;music.pos=0;music.repeats=repeat;music.playing=true;music.paused=false;audioError=0;
        if(!audioStarted){audioStarted=true;audioStart=ms();}
        fprintf(stderr,"[MusicPlay] name=%s samples=%zu rate=22050 repeat=%u volume=%u\n",name.c_str(),music.samples.size(),repeat,music.volume);return true;
    }
    int32_t musicSample(){if(!music.playing||music.paused||music.samples.empty())return 0;
        if(music.pos==music.samples.size()){if(music.repeats==1){music.playing=false;return 0;}if(music.repeats>1)--music.repeats;music.pos=0;}
        return ScalePcmVolume(music.samples[music.pos++],music.volume);
    }
    void audioEnd(U ch,Done done){
        auto& c=channels[ch];const U generation=c.generation;
        const int32_t remaining=c.repeat>0?c.repeat-1:-1;
        U info[4]={ch,static_cast<U>(remaining),c.start,c.length};wr(endInfo,info,sizeof(info));
        auto complete=[this,ch,generation,done](U keep){
            auto& channel=channels[ch];if(channel.generation!=generation){done(0);return;}
            if(keep){
                U nextData=word(endInfo+8),nextLength=word(endInfo+12);channel.repeat=static_cast<int32_t>(word(endInfo+4));
                if(nextData)channel.start=nextData;channel.length=nextLength;channel.pos=std::max<int32_t>(0,channel.loop);channel.playing=channel.start&&channel.length;
                if(getenv("PGR_AUDIO_TRACE"))fprintf(stderr,"[SoundContinue] ch=%u remaining=%d samples=%u\n",ch,channel.repeat,channel.length);
            }else channel.playing=false;
            if(!channel.playing)audioEvent("end",ch);done(0);
        };
        if(c.fn[0])call(c.fn[0],{endInfo,c.ud[0]},std::move(complete));else complete(remaining!=0);
    }

    void audioChannel(U ch,Done done){
        if(ch==soundChannels){auto& block=outputBlock;for(U i=0;i<soundBlock;++i){int64_t effect=int64_t(mixAccumulator[i])*masterVolume/256;int32_t track=musicSample();musicStemBlock[i]=int16_t(track);effectsStemBlock[i]=int16_t(std::clamp<int64_t>(effect,-32768,32767));block[i]=static_cast<int16_t>(std::clamp<int64_t>(effect+track,-32768,32767));}if(audioStemOut){audioStemOut(16,musicStemBlock.data(),soundBlock,soundRate);audioStemOut(17,effectsStemBlock.data(),soundBlock,soundRate);}if(audioStemOut)for(U ch=0;ch<soundChannels;++ch){for(auto& sample:audioStems[ch])sample=static_cast<int16_t>(ScalePcmVolume(sample,masterVolume));audioStemOut(ch,audioStems[ch].data(),soundBlock,soundRate);}if(externalMusic)externalMusic(block.data(),block.size(),masterVolume,soundAllPaused);if(audioOut)audioOut(block.data(),block.size(),soundRate);audioSamples+=soundBlock;audioWritten+=soundBlock;++mixBlocks;maxMixMs=std::max(maxMixMs,U(ms()-mixBegin));mixing=false;done(0);return;}
        auto next=[this,ch,done](U){audioChannel(ch+1,done);};auto& c=channels[ch];
        if(!c.playing||c.paused||soundAllPaused){next(0);return;}
        if(c.fn[2]&&!c.fn[1]){fatal("stereo audio generator not yet supported");return;}
        if(c.fn[1]){
            // Each generator owns a clean target. Some NFS generators overwrite it
            // even when the old shared-target mix flag was set.
            zero(mixBuf,soundBlock*2);U info[9]={ch,mixBuf,soundBlock,0,c.start,c.length,static_cast<U>(c.repeat),0,0};wr(genInfo,info,sizeof(info));
            if(getenv("PAN_GENERATOR_TRACE")&&generatorCalls<12)fprintf(stderr,"[Generator] ch=%u fn=%08x start=%08x length=%u repeat=%d rate=%u vol=%u\n",ch,c.fn[1],c.start,c.length,c.repeat,c.rate,c.volume);
            U begin=ms();++generatorCalls;call(c.fn[1],{genInfo,c.ud[1]},[this,ch,next,begin](U){maxGeneratorMs=std::max(maxGeneratorMs,U(ms()-begin));auto& samples=channelScratch;rd(mixBuf,samples.data(),samples.size()*2);for(U i=0;i<soundBlock;++i)mixAccumulator[i]+=samples[i];if(audioStemOut)audioStems[ch].assign(samples.begin(),samples.end());if(getenv("PAN_GENERATOR_TRACE")&&generatorCalls<12){int peak=0;for(auto x:samples)peak=std::max(peak,std::abs(int(x)));fprintf(stderr,"[GeneratorReturn] end=%08x extra=%08x length=%u peak=%d master=%u\n",word(genInfo+28),word(genInfo+32),word(genInfo+20),peak,masterVolume);}if(word(genInfo+28))audioEnd(ch,next);else next(0);});return;
        }
        if(!c.start||!c.length){audioEnd(ch,next);return;}
        if(c.length>16u*1024*1024){fatal("invalid PCM sample length");return;}
        std::vector<int16_t> src(c.length);rd(c.start,src.data(),src.size()*2);bool ended=false;
        for(U i=0;i<soundBlock;++i){if(c.pos>=c.length){if(c.repeat==1){ended=true;break;}if(c.repeat>1)--c.repeat;c.pos=std::clamp<int64_t>(c.loop,0,c.length-1);}int32_t sample=ScalePcmVolume(src[static_cast<size_t>(c.pos)],c.volume);mixAccumulator[i]+=sample;if(audioStemOut)audioStems[ch][i]=static_cast<int16_t>(sample);c.pos+=double(c.rate)/soundRate;}
        if(ended)audioEnd(ch,next);else next(0);
    }
    void pumpAudio(Done done,unsigned blocks=0){
        if(mixing||!audioStarted||blocks>=4){done(0);return;}
        uint64_t due=uint64_t(U(ms()-audioStart))*soundRate/1000;
        if(audioSamples+soundBlock>due){done(0);return;}
        // Bound callback work after long file loads; retain a short audible gap instead of a callback storm.
        if(due>audioSamples+soundRate/4)audioSamples=due-soundRate/4;
        if(!mixBuf){mixBuf=alloc(soundBlock*2);genInfo=alloc(36);endInfo=alloc(16);}
        mixing=true;mixBegin=ms();mixAccumulator.fill(0);if(audioStemOut)for(auto& stem:audioStems)stem.assign(soundBlock,0);audioChannel(0,[this,done,blocks](U){pumpAudio(done,blocks+1);});
    }
    bool number(const std::string& text,int64_t& value,unsigned depth=0){
        if(depth>16)return false;
        size_t at=0;bool ok=true;
        auto space=[&](){while(at<text.size()&&std::isspace(static_cast<unsigned char>(text[at])))++at;};
        std::function<int64_t()> sum,product,atom;
        atom=[&]()->int64_t{space();if(at>=text.size()){ok=false;return 0;}
            if(text[at]=='+'||text[at]=='-'){bool negative=text[at++]=='-';auto n=atom();return negative?-n:n;}
            if(text[at]=='('){++at;auto n=sum();space();if(at>=text.size()||text[at++]!=')')ok=false;return n;}
            if(text[at]=='['){size_t end=text.find(']',++at);if(end==std::string::npos){ok=false;return 0;}std::string section=text.substr(at,end-at);at=end+1;space();size_t begin=at;while(at<text.size()&&(std::isalnum(static_cast<unsigned char>(text[at]))||text[at]=='_'))++at;if(at==begin){ok=false;return 0;}auto it=config.find(lower(section+"/"+text.substr(begin,at-begin)));int64_t n=0;if(it==config.end()||!number(it->second,n,depth+1))ok=false;return n;}
            char* end=nullptr;const char* begin=text.c_str()+at;auto n=std::strtoll(begin,&end,0);if(end==begin){ok=false;return 0;}at=end-text.c_str();return n;
        };
        product=[&]()->int64_t{auto n=atom();for(;;){space();if(at>=text.size()||(text[at]!='*'&&text[at]!='/'&&text[at]!='%'))return n;char op=text[at++];auto r=atom();if((op=='/'||op=='%')&&!r){ok=false;return 0;}n=op=='*'?n*r:op=='/'?n/r:n%r;}};
        sum=[&]()->int64_t{auto n=product();for(;;){space();if(at>=text.size()||(text[at]!='+'&&text[at]!='-'))return n;char op=text[at++];auto r=product();n=op=='+'?n+r:n-r;}};
        value=sum();space();return ok&&at==text.size();
    }
    void parse(const std::string& text){std::string section;bool active=true;size_t p=0;while(p<text.size()){size_t e=text.find('\n',p);std::string line=trim(text.substr(p,e==std::string::npos?e:e-p));p=e==std::string::npos?text.size():e+1;if(line.empty()||line[0]=='#'||line.rfind("//",0)==0)continue;if(line[0]=='{'){std::string cond=lower(line.substr(1,line.find('}')-1));cond.erase(std::remove_if(cond.begin(),cond.end(),[](char c){return c==' '||c=='\t';}),cond.end());active=cond.empty()||cond=="id=any"||cond=="class=any"||cond=="os=any"||cond=="os=ngi"||cond=="os=symbian"||cond=="screensize=any"||cond=="screensize=qvga";
                if(!cond.empty()&&cond[0]=='['){size_t close=cond.find(']'),equal=cond.find("==");if(close!=std::string::npos&&equal!=std::string::npos&&equal>close){std::string key=cond.substr(1,close-1)+"/"+cond.substr(close+1,equal-close-1);auto value=config.find(key);active=value!=config.end()&&lower(trim(value->second))==cond.substr(equal+2);}}
                continue;}if(line[0]=='['){section=lower(line.substr(1,line.find(']')-1));continue;}size_t eq=line.find('=');if(active&&eq!=std::string::npos){std::string val=trim(line.substr(eq+1));if(!val.empty()&&val[0]=='"')val=val.substr(1,val.find('"',1)-1);else val=trim(val.substr(0,std::min(val.find('#'),val.find("//"))));int64_t resolved=0;if(val.find('[')!=std::string::npos&&number(val,resolved))val=std::to_string(resolved);config[section+"/"+lower(trim(line.substr(0,eq)))]=val;}}}
    U ms(){return static_cast<U>(NfsClockMs()-start);}
    bool suspendAndStop=false;
    void pollHost(bool force=false){U now=ms();if(poll&&(force||U(now-lastPoll)>=16)){lastPoll=now;poll(desired);}if(periodicLogging&&U(now-lastHeartbeat)>=5000){lastHeartbeat=now;std::fprintf(stdout,"[S3E] Heartbeat ms=%lu frame=%lu calls=%llu callbacks=%lu\n",(unsigned long)now,(unsigned long)frames,(unsigned long long)calls,(unsigned long)tasks.size());}}
    std::vector<std::pair<U,U>> surfaceCallbacks;
    unsigned surfaceWidth = 320;
    bool surfaceToggleRequested=false;
    void notifySurface(const std::shared_ptr<std::vector<std::pair<U,U>>>& callbacks, size_t at, U event, U returnValue){
        if(at==callbacks->size()){
            heap.Free(event);
            finish(returnValue);
            return;
        }
        const auto [fn,user]=(*callbacks)[at];
        call(fn,{event,user},[this,callbacks,at,event,returnValue](U result){
            (void)result;
            notifySurface(callbacks,at+1,event,returnValue);
        });
    }
    bool switchSurface(U returnValue=0){
        if(!surfaceToggleRequested)return false;
        surfaceToggleRequested=false;
        if(surfaceCallbacks.empty())return false;
        U event=alloc(20);
        if(!event)return false;
        surfaceWidth=surfaceWidth==320?400:320;
        const U change[]={1,surfaceWidth,240,0,2*surfaceWidth};
        wr(event,change,sizeof(change));
        if(getenv("RE_HW_PROBE")){
            GLES::Instance().SetDisplay(surfaceWidth,240,surfaceWidth,240,400,240);
            std::printf("[Hardware] guest surface switched to %u x 240\n",surfaceWidth);
        }
        notifySurface(std::make_shared<std::vector<std::pair<U,U>>>(surfaceCallbacks),0,event,returnValue);
        return true;
    }
    void svc(U index){if((++pollCounter&63u)==0)pollHost();if(quit){finish(0);cpu->Stop();return;}if(index==imports.size()){returned();return;}if(index>=imports.size()){fatal("invalid service index");return;}++calls;const std::string& n=imports[index];if(getenv("PGR_STATE_LIFETIME")){static U previous=0;U state=0;cpu->MemRead(G(0x4a0c4154),&state,4);if(state!=previous){U owner=heap.OwnerOf(state);fprintf(stderr,"[StateOwner] state=%08x owner=%08x size=%u service=%s\n",state,owner,heap.SizeOf(owner),n.c_str());previous=state;}}if(seen.insert(n).second)std::fprintf(stdout,"[S3E] Startup import %llu: %s\n",(unsigned long long)calls,n.c_str());R r{reg(0),reg(1),reg(2),reg(3)};if(getenv("NFS_DIAG")&&(n=="s3eKeyboardGetInt"||n=="s3ePointerGetInt"||n=="s3eMemorySetUserMemMgr"))fprintf(stderr,"[Capability] %s a0=%u a1=%08x a2=%08x\n",n.c_str(),r[0],r[1],r[2]);if(getenv("PAN_IMPORT_TRACE"))fprintf(stderr,"[Import] call=%llu name=%s lr=%08x sp=%08x args=%08x,%08x,%08x,%08x\n",(unsigned long long)calls,n.c_str(),reg(Cpu::REG_LR),reg(Cpu::REG_SP),r[0],r[1],r[2],r[3]);if(getenv("RE_HW_PROBE")&&(n.rfind("gl",0)==0||n.rfind("egl",0)==0)){
        U ret=0;
        if(GLES::Instance().Handle(n,cpu,r.data(),ret)){
            if(!quit&&n=="eglSwapBuffers"&&ret&&switchSurface(ret))return;
            finish(ret);
            if(quit)cpu->Stop();
            return;
        }
    }
    auto done=[this](U x){finish(x);};if(getenv("PGR_AUDIO_TRACE")&&n.rfind("s3eSound",0)==0)fprintf(stderr,"[PGRAudio] %s lr=%08x args=%08x,%08x,%08x,%08x\n",n.c_str(),reg(Cpu::REG_LR),r[0],r[1],r[2],r[3]);
        if(n=="s3eMemorySetInt"){fprintf(stderr,"[CapabilityUnavailable] s3eMemorySetInt property=%u value=%u\n",r[0],r[1]);finish(1);return;}
        // This guest uses secondary heap 1 only as a lifecycle token around video.
        // Allocations remain in the existing shared GuestHeap; no raw secondary arena is exposed.
        if(n=="s3eMemoryHeapCreate"){if(r[0]!=1){finish(1);return;}memoryHeaps[1]=0;finish(0);return;}
        if(n=="s3eMemoryHeapDestroy"){auto it=memoryHeaps.find(r[0]);if(it==memoryHeaps.end()){finish(1);return;}heap.Free(it->second);memoryHeaps.erase(it);finish(0);return;}
        if(n=="s3eMemoryHeapAddress"){auto it=memoryHeaps.find(r[0]);finish(it==memoryHeaps.end()?0:it->second);return;}
        if(n=="s3eMalloc"||n=="s3eMallocBase"){finish(alloc(r[0]));return;}
        if(n=="s3eRealloc"||n=="s3eReallocBase"){finish(realloc_(r[0],r[1]));return;}
        if(n=="s3eFree"||n=="s3eFreeBase"){if(getenv("PGR_HOST_WRITE_TRACE")){U state=0;cpu->MemRead(G(0x4a0c4154),&state,4);if(r[0]<=state&&uint64_t(r[0])+heap.SizeOf(r[0])>state)fprintf(stderr,"[FreeRenderState] free=%08x size=%u state=%08x lr=%08x\n",r[0],heap.SizeOf(r[0]),state,reg(Cpu::REG_LR));}heap.Free(r[0]);finish(0);return;}
        if(n=="s3eMemoryGetInt"){U x=0;if(r[0]==1)x=32u<<20;else if(r[0]==2)x=std::min<U>(32u<<20,heap.FreeBytes());else if(r[0]==3)x=heap.BytesInUse();else if(r[0]==4)x=std::min<U>(32u<<20,heap.LargestFree());finish(x);return;}
        if(n=="s3eMemorySetUserMemMgr"){if(r[0])rd(r[0],memmgr.data(),12);else memmgr.fill(0);finish(0);return;}
        if(n=="s3eMemoryGetUserMemMgr"){wr(r[0],memmgr.data(),12);finish(0);return;}
        // Original Symbian host Thumb 0x1a5c2: fgets-style, including newline.
        // The probe copies the whole software surface on Show; dirty-rectangle hints
        // need no separate host action and must not manufacture a presented frame.
        if(n=="s3eSurfaceInvalidate"){finish(0);return;}
        // Desktop probe has no pointer device: state is idle, coordinates default to zero.
        if(n=="s3ePointerGetX"||n=="s3ePointerGetY"){finish(0);return;}
        if(n=="s3eFileReadString"){
            if(!r[0]||r[1]<2||r[1]>65536){finish(0);return;}
            auto state=std::make_shared<LineRead>();state->dst=r[0];state->size=r[1];state->handle=r[2];state->scratch=alloc(1);
            if(!state->scratch){finish(0);return;}lineStep(state);return;
        }
        // Observed PGR ABI: ListDirectory(path)->handle; Next(handle,buffer,size)->0/1;
        // Close(handle). The guest filters filename suffixes itself.
        if(n=="s3eFileListDirectory"){
            std::string path=norm(str(r[0]));if(path.find("..")!=std::string::npos){finish(0);return;}
            Directory listing;std::error_code ec;
            std::filesystem::directory_iterator it(std::filesystem::path(assets)/path,ec),end;
            if(ec){finish(0);return;}
            for(;it!=end;it.increment(ec)){if(ec)break;listing.names.push_back(it->path().filename().string());}
            if(ec){finish(0);return;}
            std::sort(listing.names.begin(),listing.names.end());U h=alloc(4);if(!h){finish(0);return;}
            fprintf(stderr,"[PGRDirectory] path=%s entries=%zu handle=%08x\n",path.c_str(),listing.names.size(),h);
            directories.emplace(h,std::move(listing));finish(h);return;
        }
        if(n=="s3eFileListNext"){
            auto it=directories.find(r[0]);if(it==directories.end()||!r[1]||!r[2]||it->second.next>=it->second.names.size()){finish(1);return;}
            auto name=it->second.names[it->second.next++].substr(0,r[2]-1);wr(r[1],name.c_str(),name.size()+1);finish(0);return;
        }
        if(n=="s3eFileListClose"){auto it=directories.find(r[0]);if(it!=directories.end()){heap.Free(r[0]);directories.erase(it);}finish(0);return;}
        // PGR bundled Symbian host, Thumb 0x1c058 / 0x1c09c:
        // state defaults to 0x1000, optionally [s3e] License; property 3 returns it.
        // Other properties remain unsupported until their ABI is needed and verified.
        if(n=="s3eLicenseGetInt"&&r[0]==3){
            U status=0x1000;auto it=config.find("s3e/license");int64_t configured=0;
            if(it!=config.end()&&number(it->second,configured))status=static_cast<U>(configured);
            fprintf(stderr,"[PGRLicense] property=3 status=%08x source=%s\n",status,it==config.end()?"bundled-host default":"configuration");
            finish(status);return;
        }
        if(n=="s3eConfigGetInt"||n=="s3eConfigGetString"){auto i=config.find(lower(str(r[0])+"/"+str(r[1])));if(getenv("NFS_DIAG")||getenv("PAN_CONFIG_TRACE"))fprintf(stderr,"[Config] %s/%s = %s\n",str(r[0]).c_str(),str(r[1]).c_str(),i==config.end()?"<unset>":i->second.c_str());if(i==config.end()){finish(1);return;}if(n=="s3eConfigGetInt"){int64_t resolved=0;if(!number(i->second,resolved)){finish(1);return;}word(r[2],static_cast<U>(resolved));}else{auto s=i->second.substr(0,254);wr(r[2],s.c_str(),s.size()+1);}finish(0);return;}
        if(n=="s3eTimerSetTimer"){
            bool ok=timers.Add(NfsClockMs()-start,r[0],r[1],r[2]);
            fprintf(stderr,"[TimerSet] frame=%lu delay=%lu callback=%08lx user=%08lx result=%d\n",(unsigned long)frames,(unsigned long)r[0],(unsigned long)r[1],(unsigned long)r[2],ok?0:1);
            finish(ok?0:1);return;
        }
        if(n=="s3eTimerGetMs"){uint64_t now=NfsClockMs()-start;set(1,U(now>>32));finish(U(now));return;}if(n=="s3eTimerGetInt"){finish(r[0]==0?1:0);return;}
        if(n=="s3eGLGetNativeWindow"&&getenv("RE_HW_PROBE")){finish(1);return;}
        if(n=="s3eGLGetInt"&&getenv("RE_HW_PROBE")){fprintf(stderr,"[HardwareProbe] s3eGLGetInt(%u)\n",r[0]);finish(r[0]==0?0x110:0);return;}
        if(n=="s3eAccelerometerGetInt"||n=="s3eDeviceGetInt"||n=="s3eGLGetInt"){finish(0);return;}
        if(n=="s3eAccelerometerStart"){finish(1);return;}
        if(n=="s3eAccelerometerStop"){finish(0);return;}
        if(n=="s3eAccelerometerGetX"||n=="s3eAccelerometerGetY"||n=="s3eAccelerometerGetZ"){finish(0);return;}
        if(n=="s3eDeviceRegister"){deviceCallbacks[r[0]]={r[1],r[2]};if(getenv("PAN_LIFECYCLE_TRACE"))fprintf(stderr,"[DeviceRegister] event=%u callback=%08x user=%08x\n",r[0],r[1],r[2]);finish(0);return;}
        if(n=="s3eDeviceUnRegister"){deviceCallbacks.erase(r[0]);finish(0);return;}
        if(n=="s3eDeviceCheckQuitRequest"){finish(quit);return;}
        if(n=="s3eDeviceExit"||n=="s3eDeviceRequestQuit"){finish(0);quit=true;cpu->Stop();return;}
        const unsigned width=surfaceWidth;
        if(n=="s3eSurfaceRegister"){if(r[0]==1&&r[1])surfaceCallbacks.emplace_back(r[1],r[2]);finish(0);return;}
        if(n=="s3eSurfaceUnRegister"){if(r[0]==1)surfaceCallbacks.erase(std::remove_if(surfaceCallbacks.begin(),surfaceCallbacks.end(),[&](const auto& cb){return cb.first==r[1];}),surfaceCallbacks.end());finish(0);return;}
        if(n=="s3eSurfaceGetInt"){
            // The direct background blitter queries property 7 at 0x4A012064
            // and divides the byte pitch by two for RGB565 row stepping.
            // It shares the unrotated 320x240 framebuffer with the GX renderer.
            U value=r[0]==0?width:r[0]==1?240:(r[0]==2||r[0]==7)?2*width:r[0]==8?1:0;
            if(getenv("PAN_SURFACE_TRACE")){static std::set<U> observed;if(observed.insert(r[0]).second)fprintf(stderr,"[Surface] property=%u value=%u lr=%08x\n",r[0],value,reg(Cpu::REG_LR));}
            finish(value);return;
        }
        if(n=="s3eSurfacePtr"){finish(FB_BASE);return;}
        if(n=="s3eSurfaceShow"){++frames;measureFrame();std::vector<uint16_t> image(width*240);rd(FB_BASE,image.data(),image.size()*2);if(present)present(frames,image.data(),desired);if(periodicLogging&&(frames==1||frames%300==0))std::fprintf(stdout,"[S3E] Frame %lu; heap %lu KB; calls %llu\n",(unsigned long)frames,(unsigned long)(heap.BytesInUse()/1024),(unsigned long long)calls);if(!quit&&(!limit||frames<limit)&&switchSurface())return;finish(0);if(limit&&frames>=limit){quit=true;cpu->Stop();}return;}
        if(n=="s3ePointerRegister"){pointerCallbacks[r[0]]={r[1],r[2]};finish(0);return;}
        if(n=="s3ePointerUnRegister"){pointerCallbacks.erase(r[0]);finish(0);return;}
        if(n=="s3eKeyboardRegister"){keyCallbacks[r[0]]={r[1],r[2]};finish(0);return;}if(n=="s3eKeyboardUnRegister"){keyCallbacks.erase(r[0]);finish(0);return;}
        if(n=="s3eKeyboardUpdate"){updateKeys();return;}if(n=="s3eKeyboardGetState"){if(getenv("NFS_KEY_TRACE")){static std::set<U> codes;if(codes.insert(r[0]).second)fprintf(stderr,"[KeyQuery] code=%u caller=%08x\n",r[0],reg(Cpu::REG_LR));}if(getenv("PAN_KEY_TRACE")&&r[0]<256&&keyState[r[0]]){static std::map<U,U> last;U state=keyState[r[0]];if(last[r[0]]!=state){last[r[0]]=state;fprintf(stderr,"[KeyConsumed] frame=%u code=%u state=%u lr=%08x\n",frames,r[0],state,reg(Cpu::REG_LR));}}finish(r[0]<256?keyState[r[0]]:0);return;}
        if(n=="s3eKeyboardGetDisplayName"){
            // Observed guest ABI: output buffer, S3E key, display-format flag.
            const std::map<U,std::string> labels={{9,"LEFT"},{10,"UP"},{11,"RIGHT"},{12,"DOWN"},{73,"LSK"},{72,"RSK"},{77,"C"},{78,"OK"},{200,"A"},{201,"B"}};
            auto it=labels.find(r[1]);std::string label=it==labels.end()?"?":it->second;if(r[1]>=13&&r[1]<=22)label=std::string(1,static_cast<char>('0'+r[1]-13));
#ifdef __3DS__
            const bool consoleLabels=true;
#else
            const bool consoleLabels=getenv("RE_CONSOLE_UI")!=nullptr;
#endif
            if(consoleLabels){
                const std::map<U,std::string> console={{13,"Y"},{14,"*"},{15,"U"},{16,"*"},{17,"L"},{18,"A"},{19,"R"},{20,"*"},{21,"D"},{22,"*"},{76,"X"},{77,"L"},{78,"A"},{208,"A"},{209,"X"},{210,"B"}};
                auto k=console.find(r[1]);if(k!=console.end())label=k->second;
            }
            static std::set<std::pair<U,U>> shownLabels;if(shownLabels.insert({r[1],r[2]}).second)std::fprintf(stdout,"[S3E] Key label %u -> %s (format %u)\n",r[1],label.c_str(),r[2]);
            wr(r[0],label.c_str(),label.size()+1);finish(0);return;
        }
        if(n=="s3eKeyboardAnyKey"){U v=0;for(U k=1;k<256;++k)if(keyState[k]&3){v=k;break;}finish(v);return;}
        if(n=="s3eKeyboardClearState"){keyState.fill(0);finish(0);return;}
        if(n=="s3ePointerGetInt"||n=="s3eKeyboardGetInt"||n=="s3ePointerUpdate"||n=="s3ePointerGetState"||n=="s3ePointerGetY"){finish(0);return;}
        if(n=="s3eSoundPauseAllChannels"){if(getenv("PAN_MUSIC_TRACE"))fprintf(stderr,"[SoundGroup] pause\n");soundAllPaused=true;finish(0);return;}
        if(n=="s3eSoundResumeAllChannels"){if(getenv("PAN_MUSIC_TRACE"))fprintf(stderr,"[SoundGroup] resume\n");soundAllPaused=false;finish(0);return;}
        if(n=="s3eSoundStopAllChannels"){for(auto& channel:channels)channel.playing=channel.paused=false;finish(0);return;}
        if(n=="s3eSoundGetInt"){U value=0;if(r[0]==0)value=masterVolume;else if(r[0]==1||r[0]==2)value=soundRate;else if(r[0]==3)value=soundChannels;else if(r[0]==4){for(auto& c:channels)value+=c.playing;}else if(r[0]==5)value=1;else if(r[0]==6)value=256;finish(value);return;}
        if(n=="s3eSoundSetInt"){if(r[0]==0)masterVolume=std::min<U>(256,r[1]);finish(0);return;}
        if(n=="s3eSoundGetFreeChannel"){U free=0xffffffff;for(U ch=0;ch<soundChannels;++ch)if(!channels[ch].playing){free=ch;break;}finish(free);return;}
        if(n=="s3eSoundChannelRegister"||n=="s3eSoundChannelUnRegister"){if(r[0]>=soundChannels||r[1]>=4){finish(1);return;}auto& c=channels[r[0]];audioEvent(n.c_str(),r[0]);c.fn[r[1]]=n=="s3eSoundChannelRegister"?r[2]:0;c.ud[r[1]]=n=="s3eSoundChannelRegister"?r[3]:0;if(traceAudio)std::fprintf(stdout,"[Audio] %s ch=%u event=%u fn=%08x\n",n.c_str(),r[0],r[1],r[2]);finish(0);return;}
        if(n=="s3eSoundChannelSetInt"){if(r[0]>=soundChannels){finish(1);return;}auto& c=channels[r[0]];if(r[1]==1)c.rate=r[2];else if(r[1]==2)c.uservar=r[2];else if(r[1]==3)c.volume=std::min<U>(r[2],256);else if(r[1]==4)c.paused=r[2]!=0;else{finish(1);return;}finish(0);return;}
        if(n=="s3eSoundChannelGetInt"){if(getenv("PAN_STATUS_TRACE")&&r[1]==0){static unsigned count=0;if(count++<80)fprintf(stderr,"[SoundStatus] ch=%u playing=%u lr=%08x\n",r[0],r[0]<soundChannels?channels[r[0]].playing:0,reg(14));}U v=0;if(r[0]<soundChannels){auto& c=channels[r[0]];if(r[1]==0)v=c.playing;else if(r[1]==1)v=c.rate;else if(r[1]==2)v=c.uservar;else if(r[1]==3)v=c.volume;else if(r[1]==4)v=c.playing;else if(r[1]==5)v=c.paused;}finish(v);return;}
        if(n=="s3eSoundChannelPlay"){if(r[0]>=soundChannels){finish(1);return;}auto& c=channels[r[0]];++c.generation;c.start=r[1];c.length=r[2];c.repeat=static_cast<int32_t>(r[3]);c.loop=static_cast<int32_t>(word(reg(Cpu::REG_SP)));c.pos=0;c.playing=true;c.paused=false;if(!audioStarted){audioStarted=true;audioStart=ms();}++soundStarts;audioEvent("play",r[0]);if(traceAudio)std::fprintf(stdout,"[Audio] Play ch=%u start=%08x samples=%u repeat=%d generator=%08x\n",r[0],c.start,c.length,c.repeat,c.fn[1]);finish(0);return;}
        if(n=="s3eSoundChannelStop"||n=="s3eSoundChannelPause"||n=="s3eSoundChannelResume"){if(r[0]>=soundChannels){finish(1);return;}auto& c=channels[r[0]];audioEvent(n.c_str(),r[0]);if(getenv("PAN_STATUS_TRACE"))fprintf(stderr,"[SoundStopCaller] ch=%u playing=%u lr=%08x\n",r[0],c.playing,reg(14));if(n=="s3eSoundChannelStop"){++c.generation;c.playing=c.paused=false;}else c.paused=n=="s3eSoundChannelPause";finish(0);return;}
        if(n=="s3eAudioIsCodecSupported"){U result=r[0]==2&&mp3.Available();fprintf(stderr,"[AudioCodec] codec=%u supported=%u\n",r[0],result);finish(result);return;}
        if(n=="s3eAudioGetInt"){U result=r[0]==0?music.volume:r[0]==1?(music.playing?(music.paused?2:1):0):0;static std::set<std::pair<U,U>> reported;if(reported.insert({r[0],result}).second)fprintf(stderr,"[AudioProperty] property=%u value=%u\n",r[0],result);finish(result);return;}
        if(n=="s3eAudioSetInt"){if(r[0]!=0){fprintf(stderr,"[AudioPropertyUnsupported] property=%u value=%u\n",r[0],r[1]);finish(1);return;}music.volume=std::min<U>(r[1],256);fprintf(stderr,"[MusicVolume] value=%u\n",music.volume);finish(0);return;}
        if(n=="s3eAudioPlay"){
            std::string name=norm(str(r[0]));if(name.find("..")!=std::string::npos){audioError=1;finish(1);return;}
            name=resolveAsset(name);std::ifstream file(assets+"/"+name,std::ios::binary);std::vector<uint8_t> data;if(file)data.assign(std::istreambuf_iterator<char>(file),{});
            if(data.empty()){fprintf(stderr,"[MusicError] missing=%s\n",name.c_str());audioError=1;finish(1);return;}
            finish(playMusic(data,r[1],name)?0:1);return;
        }
        if(n=="s3eAudioPlayFromBuffer"){if(r[1]>(16u<<20)){audioError=1;finish(1);return;}std::vector<uint8_t> data(r[1]);rd(r[0],data.data(),data.size());if(failed)return;std::string name="buffer:"+std::to_string(crc32(0,data.data(),data.size()));finish(playMusic(data,r[2],name)?0:1);return;}
        if(n=="s3eAudioStop"){if(getenv("PAN_MUSIC_TRACE"))fprintf(stderr,"[MusicControl] stop position=%zu playing=%u\n",music.pos,music.playing?1:0);music.playing=music.paused=false;music.pos=0;finish(0);return;}
        if(n=="s3eAudioPause"||n=="s3eAudioResume"){music.paused=n=="s3eAudioPause";finish(0);return;}
        if(n=="s3eAudioGetError"){U error=audioError;audioError=0;finish(error);return;}
        if(n.rfind("s3eVideo",0)==0&&getenv("PAN_VIDEO_TRACE"))fprintf(stderr,"[VideoABI] %s args=%08x,%08x,%08x,%08x lr=%08x\n",n.c_str(),r[0],r[1],r[2],r[3],reg(14));
        if(n=="s3eVideoPlayFromBuffer"){
            if(!videoPlayer||r[1]>(8u<<20)){finish(1);return;}
            std::vector<uint8_t> data(r[1]);rd(r[0],data.data(),data.size());if(failed)return;
            U crc=crc32(0,data.data(),data.size());std::string clip;
            if(r[1]==659333&&crc==0xd4e821f9)clip="intro.mpg";
            if(r[1]==730362&&crc==0x2ac860c3)clip="ending.mpg";
            if(clip.empty()){fprintf(stderr,"[VideoUnknown] bytes=%u crc=%08x\n",r[1],crc);finish(1);return;}
            videoRequest={r[2],r[3],word(reg(13)),word(reg(13)+4),word(reg(13)+8),videoVolume};
            videoPath=assets+"/../video/"+clip;videoPlaying=videoPending=true;finish(0);return;
        }
        if(n=="s3eVideoSetInt"){if(r[0]!=0){finish(1);return;}videoVolume=std::min<U>(r[1],256);finish(0);return;}
        if(n=="s3eVideoGetInt"){
            if(r[0]==1&&videoPending&&videoPlaying){
                videoPending=false;videoRequest.volume=videoVolume;U began=ms();
                int result=videoPlayer(videoPath,videoRequest);audioStart+=U(ms()-began);videoPlaying=false;
                fprintf(stderr,"[VideoReturn] path=%s result=%d callback=%08x\n",videoPath.c_str(),result,videoCallbacks.count(0)?videoCallbacks[0].first:0);
                auto cb=videoCallbacks.find(0);if(cb==videoCallbacks.end()){finish(0);return;}
                call(cb->second.first,{0,cb->second.second},[this](U){finish(0);});return;
            }
            finish(r[0]==0?videoVolume:r[0]==1?videoPlaying:0);return;
        }
        if(n=="s3eVideoStop"){videoPlaying=videoPending=false;finish(0);return;}
        if(n=="s3eVideoPlay"){finish(1);return;}
        if(n=="s3eVideoRegister"){videoCallbacks[r[0]]={r[1],r[2]};finish(0);return;}
        if(n=="s3eVideoIsCodecSupported"){finish(r[0]==1&&bool(videoPlayer));return;} // Only the mapped MPEG-4 source contract is exposed.
        if(n=="s3eAudioIsPlaying"){finish(music.playing&&!music.paused);return;}
        if(n=="s3eInetHtons"){finish(((r[0]&255)<<8)|((r[0]>>8)&255));return;}
        if(n=="s3eFileGetFree"){
            if(r[0]!=1){fatal("unsupported free-space drive "+std::to_string(r[0]));return;}
            uint64_t bytes=UINT64_MAX;int error=0;
#ifdef __3DS__
            FS_Archive archive;Result rc=FSUSER_OpenArchive(&archive,ARCHIVE_SDMC,fsMakePath(PATH_EMPTY,""));
            if(R_SUCCEEDED(rc)){u64 available=0;rc=FSUSER_GetFreeBytes(&available,archive);FSUSER_CloseArchive(archive);if(R_SUCCEEDED(rc))bytes=available;}
            error=static_cast<int>(rc);
#else
            std::error_code ec;auto info=std::filesystem::space(saves,ec);bytes=ec?UINT64_MAX:info.available;error=ec.value();
#endif
            fprintf(stderr,"[FreeSpace] drive=%u available=%llu error=%d\n",r[0],(unsigned long long)bytes,error);set(1,U(bytes>>32));finish(U(bytes));return;
        }
        if(n=="s3eFileAddUserFileSys"){std::array<U,11> t;rd(r[0],t.data(),44);fs.push_back(t);finish(0);return;}
        if(n=="s3eFileOpen"){++fileApiOpens;std::string path=norm(str(r[0]));std::fprintf(stdout,"[S3E] Open %s\n",path.c_str());U pc=reg(Cpu::REG_PC),lr=reg(Cpu::REG_LR);open(r,[this,path,pc,lr,done](U h){recordFile(path,h,lr);if(path==HybridTrace::Target()){auto host=files.find(h);hybrid.Open(h,host!=files.end()&&host->second.name=="overrides/"+path,pc,lr);}done(h);});return;}
        if(n=="s3eFileGetFileInt"){
            if(r[1]!=4){fatal("unsupported file-stat property "+std::to_string(r[1]));return;}
            U mode=alloc(4);wr(mode,"rb",3);std::string name=str(r[0]);
            open({r[0],mode,0,0},[this,mode,name](U h){heap.Free(mode);if(!h){set(Cpu::REG_R1,0xffffffffu);finish(0xffffffffu);return;}getSize(h,[this,h,name](U bytes){close(h,[this,name,bytes](U){std::fprintf(stdout,"[S3E] File size %s = %lu\n",name.c_str(),(unsigned long)bytes);set(Cpu::REG_R1,0);finish(bytes);});});});return;
        }
        if(n=="s3eFileCheckExists"){if(getenv("NFS_RESOURCE_TRACE"))fprintf(stderr,"[Exists] %s\n",str(r[0]).c_str());U m=alloc(4);const char mode[]="rb";wr(m,mode,3);open({r[0],m,0,0},[this,m](U h){heap.Free(m);if(!h){finish(0);return;}close(h,[this](U){finish(1);});});return;}
        if(n=="s3eFileRead"){U pc=reg(Cpu::REG_PC),lr=reg(Cpu::REG_LR),stack=reg(Cpu::REG_SP),parent=hybrid.active;bool watched=hybrid.Has(r[3]);U owner=watched?heap.OwnerOf(r[0]):0;int64_t capacity=owner?int64_t(owner)+heap.SizeOf(owner)-r[0]:-1;if(watched)hybrid.active=r[3];read(r,[this,r,pc,lr,stack,capacity,parent,watched,done](U count){if(watched){std::vector<uint8_t> bytes(uint64_t(count)*r[1]);rd(r[0],bytes.data(),bytes.size());hybrid.Read(r[3],bytes,uint64_t(r[1])*r[2],pc,lr,r[0],stack,capacity);hybrid.active=parent;}done(count);});return;}
        if(n=="s3eFileClose"){U pc=reg(Cpu::REG_PC),lr=reg(Cpu::REG_LR);close(r[0],[this,r,pc,lr,done](U result){hybrid.Close(r[0],result,pc,lr);done(result);});return;}
        if(n=="s3eFileSeek"){U pc=reg(Cpu::REG_PC),lr=reg(Cpu::REG_LR);seek(r,[this,r,pc,lr,done](U result){hybrid.Seek(r[0],int32_t(r[1]),r[2],result,pc,lr);done(result);});return;}
        if(n=="s3eFileTell"){U pc=reg(Cpu::REG_PC),lr=reg(Cpu::REG_LR);tell(r[0],[this,r,pc,lr,done](U pos){hybrid.Tell(r[0],pos,pc,lr);done(pos);});return;}
        if(n=="s3eFileGetSize"){U pc=reg(Cpu::REG_PC),lr=reg(Cpu::REG_LR);getSize(r[0],[this,r,pc,lr,done](U size){hybrid.Size(r[0],size,pc,lr);done(size);});return;}
        if(n=="s3eFileEOF"){auto g=handles.find(r[0]);if(g!=handles.end())call(fs[g->second][2],{r[0]},done);else{auto f=files.find(r[0]);finish(f==files.end()||f->second.pos>=f->second.data.size());}return;}
        if(n=="s3eFileGetChar"){U p=alloc(1);read({p,1,1,r[0]},[this,p](U got){uint8_t b=0;if(got)rd(p,&b,1);heap.Free(p);finish(got?b:0xffffffffu);});return;}
        if(n=="s3eFileOpenFromMemory"){File f;f.data.resize(r[1]);rd(r[0],f.data.data(),f.data.size());f.backing=r[0];f.name="memory@"+std::to_string(r[0]);U h=alloc(64);files[h]=std::move(f);finish(h);return;}
        if(n=="s3eFileWrite"){auto f=files.find(r[3]);if(f==files.end()||!f->second.backing){fatal("unsupported file write");return;}File& q=f->second;size_t count=std::min<uint64_t>(uint64_t(r[1])*r[2],q.pos<q.data.size()?q.data.size()-q.pos:0);rd(r[0],q.data.data()+q.pos,count);wr(q.backing+q.pos,q.data.data()+q.pos,count);q.pos+=count;finish(r[1]?count/r[1]:0);return;}
        if(n=="s3eSecureStorageGet"){std::vector<char> d;secureError=SaveStore(saves).Read(d,r[1]);fprintf(stderr,"[SecureRead] requested=%u returned=%zu error=%u crc32=%08lx\n",r[1],d.size(),secureError,(unsigned long)crc32(0,reinterpret_cast<const Bytef*>(d.data()),d.size()));if(!secureError)wr(r[0],d.data(),d.size());finish(secureError?1:0);return;}
        if(n=="s3eSecureStorageGetError"){U error=secureError;secureError=0;finish(error);return;}
        if(n=="s3eSecureStoragePut"){std::vector<char>d(r[1]);rd(r[0],d.data(),d.size());if(failed)return;secureError=SaveStore(saves).Write(d)?0:1;fprintf(stderr,"[SecureWrite] bytes=%zu error=%u crc32=%08lx\n",d.size(),secureError,(unsigned long)crc32(0,reinterpret_cast<const Bytef*>(d.data()),d.size()));finish(secureError?1:0);return;}
        if(n=="s3eCompressionDecomp"){
            U method=word(reg(Cpu::REG_SP)),dst=word(r[2]),capacity=word(r[3]);
            if(method!=2){fatal("unsupported one-shot compression method "+std::to_string(method));return;}
            if(!dst||capacity>(64u<<20)||r[1]>(64u<<20)){fatal("invalid one-shot decompression buffers");return;}
            std::vector<uint8_t> input(r[1]),output(capacity);rd(r[0],input.data(),input.size());if(failed)return;
            uLongf produced=capacity;int rc=uncompress(output.data(),&produced,input.data(),input.size());
            fprintf(stderr,"[OneShotDecode] method=%u src=%08x input=%u dst=%08x capacity=%u produced=%lu rc=%d crc32=%08lx\n",method,r[0],r[1],dst,capacity,(unsigned long)produced,rc,(unsigned long)crc32(0,output.data(),produced<=capacity?produced:0));
            if(rc==Z_OK){wr(dst,output.data(),produced);word(r[3],produced);}finish(rc==Z_OK?0:1);return;
        }
        if(n=="s3eCompressionDecompInit"){if(r[0]!=0){fatal("unsupported compression");return;}U h=alloc(16);auto d=std::make_shared<Decoder>();d->reader=r[1];d->user=r[2];d->request=alloc(8);d->buffer=alloc(4096);decoders[h]=d;finish(h);return;}
        if(n=="s3eCompressionDecompRead"){auto d=decoders.find(r[0]);if(d==decoders.end()){fatal("unknown decoder");return;}auto s=std::make_shared<DecompRead>();s->d=d->second;s->dst=r[1];s->countptr=r[2];s->need=word(r[2]);decompStep(s);return;}
        if(n=="s3eCompressionDecompFinal"){auto d=decoders.find(r[0]);if(d!=decoders.end()){heap.Free(d->second->buffer);heap.Free(d->second->request);decoders.erase(d);heap.Free(r[0]);}finish(0);return;}
        if(n=="s3eDebugTraceLine"){std::fprintf(stdout,"[Guest] %s %s\n",str(r[0]).c_str(),str(r[1]).c_str());finish(0);return;}
        if(n=="s3eDebugErrorShow"||n=="s3eDebugAssertShow"){fatal(n+": "+str(r[1]));return;}
        if(n=="s3eExtGet"){if(getenv("NFS_DIAG"))fprintf(stderr,"[Ext] %s out=%08x\n",str(r[0]).c_str(),r[1]);finish(1);return;}
        if((n=="s3eDeviceCheckPauseRequest"||n=="s3eDeviceYield")&&suspendAndStop){
            suspendAndStop=false;auto it=deviceCallbacks.find(0);
            if(it==deviceCallbacks.end()){fatal("diagnostic suspend has no registered callback");return;}
            fprintf(stderr,"[DiagnosticSuspend] callback=%08x\n",it->second.first);
            call(it->second.first,{0,it->second.second},[this](U){fprintf(stderr,"[DiagnosticSuspend] callback returned; stopping guest\n");finish(0);quit=true;cpu->Stop();});return;
        }
        if(n=="s3eDeviceYield"){pollHost(true);
#ifdef __3DS__
            svcSleepThread(r[0]?1000000:0);
#endif
            pumpAudio([this](U){pumpTimers([this](U){finish(0);});});return;}
        static const std::set<std::string> noops={"s3eDeviceCheckPauseRequest","s3eDeviceBacklightOn","s3eSurfaceSetup","s3eSoundSetInt","s3eAudioSetInt","s3eSoundChannelRegister","s3eSoundChannelUnRegister","s3eAudioRegister","s3eVibraGetInt","s3eVibraSetInt","s3eVibraVibrate","s3eVibraStop"};
        if(noops.count(n)){finish(0);return;}fatal("unsupported import "+n+" caller "+std::to_string(reg(Cpu::REG_LR)));
    }
};
S3ERuntime::S3ERuntime(Cpu* c,const std::string&a,const std::string&s):p(new Impl(c,a,s)){}
S3ERuntime::~S3ERuntime()=default;
void S3ERuntime::Init(const std::vector<std::string>& i,const std::string& c){p->imports=i;p->parse(c);
    if(getenv("RE_HW_PROBE")){
        InstallProbeHost();
        auto& gl=GLES::Instance();
        gl.SetGuestAlloc([this](uint32_t size){return p->alloc(size);});
#ifdef __3DS__
        gl.SetDisplay(320,240,320,240,400,240);
#else
        gl.SetDisplay(320,240,320,240,320,240);
#endif
        gl.SetFrameCallback([this](const uint32_t* bgra,int w,int h){
#ifdef __3DS__
            if(!bgra){
                ++p->frames;
                p->measureFrame();
                if(p->present)p->present(p->frames,nullptr,p->desired);
                return;
            }
#endif
            if(!bgra||w<int(p->surfaceWidth)||h!=240)return;
            ++p->frames;
            p->measureFrame();
            const auto width=p->surfaceWidth;
            std::vector<uint16_t> rgb(width*h);
            for(unsigned i=0;i<rgb.size();++i){
                const auto px=bgra[(i/width)*w+(w-width)/2+i%width];
                rgb[i]=((px>>8)&0xf800)|((px>>5)&0x07e0)|((px>>3)&31);
            }
            if(p->present)p->present(p->frames,rgb.data(),p->desired);
            if(p->limit&&p->frames>=p->limit)p->quit=true;
        });
        p->config["gx/rasterisation"]="HW";if(const auto* style=getenv("RE_HW_STYLE"))p->config["resmanager/resbuildstyle"]=style;}
#ifdef __3DS__
const bool consoleUi=true;
#else
const bool consoleUi=getenv("RE_CONSOLE_UI")!=nullptr;
#endif
if(consoleUi&&!p->consoleUi.Install())p->fatal("Resident Evil UI hook signature mismatch");
if(getenv("RE_RESOURCE_TRACE")){
 int enterHook=p->cpu->AddCodeHook([](Cpu*,uint64_t,uint32_t,void* user){auto* p=static_cast<Impl*>(user);p->resourceRequests[p->reg(Cpu::REG_SP)]={p->reg(0),p->reg(1),p->reg(2),p->reg(Cpu::REG_LR)};},p.get(),G(0x4a090df4),G(0x4a090df4));
 int resultHook=p->cpu->AddCodeHook([](Cpu*,uint64_t,uint32_t,void* user){auto* p=static_cast<Impl*>(user);auto it=p->resourceRequests.find(p->reg(Cpu::REG_SP)+32);if(it!=p->resourceRequests.end()){auto q=it->second;p->recentResources.push_back({p->frames,q.group,q.name,q.lr,p->reg(5)});if(p->recentResources.size()>32)p->recentResources.pop_front();if(!p->reg(5)){U type=0;p->cpu->MemRead(q.group+28,&type,4);fprintf(stderr,"[MissingResource] frame=%u group=%08x type=%08x name=%08x caller=%08x\n",p->frames,q.group,type,q.name,q.lr);p->resourceContext();}p->resourceRequests.erase(it);}},p.get(),G(0x4a090e2c),G(0x4a090e2c));
 fprintf(stderr,"[ResourceDiagnostics] entryHook=%d resultHook=%d\n",enterHook,resultHook);
}
// Observe the actual keypad state's enter/leave virtual functions. Native uses
// pointer hooks, leaving the guest instructions intact (no extra interpreter forms).
{ U enter=0,leave=0;p->cpu->MemRead(G(0x4a0f21c8),&enter,4);p->cpu->MemRead(G(0x4a0f21cc),&leave,4);
 if(enter!=(G(0x4a099ee4)|1)||leave!=(G(0x4a099c88)|1))p->fatal("keypad state signature mismatch");
 else {
  int a=p->cpu->AddCodeHook([](Cpu*,uint64_t,uint32_t,void* u){auto* p=static_cast<Impl*>(u);p->keypadOpen=true;p->keypadObject=p->reg(0);p->keypadKeys.clear();p->keypadPulseRelease=false;fprintf(stderr,"[KeypadUI] open frame=%lu\n",(unsigned long)p->frames);},p.get(),G(0x4a099ee4),G(0x4a099ee4));
  int b=p->cpu->AddCodeHook([](Cpu*,uint64_t,uint32_t,void* u){auto* p=static_cast<Impl*>(u);p->keypadOpen=false;p->keypadObject=0;p->keypadKeys.clear();p->keypadPulseRelease=false;fprintf(stderr,"[KeypadUI] close frame=%lu\n",(unsigned long)p->frames);},p.get(),G(0x4a099c88),G(0x4a099c88));
  if(a||b)p->fatal("keypad state hooks unavailable");else fprintf(stderr,"[KeypadUI] state hooks ready\n");
 }
}
p->cpu->WriteTrampoline(TRAMPOLINE_BASE+i.size()*8,i.size());p->cpu->AddSvcHook([](Cpu* c,uint32_t,void* user){uint32_t pc=0;c->RegRead(Cpu::REG_PC,&pc);static_cast<Impl*>(user)->svc((pc-TRAMPOLINE_BASE-4)/8);},p.get());}
void S3ERuntime::SetFrameCallback(std::function<void(U,const uint16_t*,Keys&)> f){p->present=std::move(f);}
void S3ERuntime::SetPollCallback(std::function<void(Keys&)> f){p->poll=std::move(f);}
void S3ERuntime::SetAudioCallback(std::function<void(const int16_t*,size_t,U)> f){p->audioOut=std::move(f);}
void S3ERuntime::SetChannelAudioCallback(std::function<void(U,const int16_t*,size_t,U)> f){p->audioStemOut=std::move(f);}
void S3ERuntime::RequestQuit(){p->quit=true;p->cpu->Stop();}
void S3ERuntime::RequestSuspendAndStop(){p->suspendAndStop=true;}
int S3ERuntime::Run(U e,U limit){p->limit=limit;int err=p->cpu->Start(e,0xDEADBEEF,getenv("PAN_INSTRUCTION_LIMIT")?std::strtoull(getenv("PAN_INSTRUCTION_LIMIT"),nullptr,0):0);if((err||p->failed)&&getenv("RE_RESOURCE_TRACE"))p->resourceContext();p->reportPerformance();std::fprintf(stdout,"[S3E] End: error=%d failed=%d frame=%lu heap peak=%lu KB\n",err,p->failed,(unsigned long)p->frames,(unsigned long)(p->heap.PeakInUse()/1024));return err?err:p->failed?1:0;}
uint32_t S3ERuntime::Frames()const{return p->frames;}bool S3ERuntime::Failed()const{return p->failed;}

uint32_t S3ERuntime::TakeConsolePrompts(){return p->consoleUi.Take();}

void S3ERuntime::SetVideoPlayer(VideoPlayer player){p->videoPlayer=std::move(player);}

void S3ERuntime::SetExternalMusicCallback(std::function<void(int16_t*,size_t,U,bool)> fn){p->externalMusic=std::move(fn);if(p->externalMusic&&!p->audioStarted){p->audioStarted=true;p->audioStart=p->ms();}}
std::string S3ERuntime::RaceCity()const{return p->raceCity;}

uint32_t S3ERuntime::MasterVolume()const{return p->masterVolume;}

void S3ERuntime::PrepareStreamChecks(){p->quit=false;p->limit=0;}

bool S3ERuntime::KeypadOpen()const{return p->keypadOpen;}
bool S3ERuntime::QueueKeypadKey(uint32_t key){if(!p->keypadOpen||key>=256||p->keypadKeys.size()>=32)return false;p->keypadKeys.push_back(key);return true;}

unsigned S3ERuntime::SurfaceWidth() const {return p->surfaceWidth;}

void S3ERuntime::RequestDisplayToggle(){p->surfaceToggleRequested=true;}
