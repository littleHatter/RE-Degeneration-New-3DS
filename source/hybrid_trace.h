#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <map>
#include <string>
#include <filesystem>
#include <vector>
#include <zlib.h>
#include <stdexcept>
class HybridTrace {
 struct Stream{unsigned id;std::string mode,archive;int64_t position=0,size=-1;FILE* dump=nullptr;};
 std::map<uint32_t,Stream> streams;FILE* records=nullptr;std::string directory;unsigned serial=0;
 static std::string quote(const std::string&s){std::string r="\"";for(unsigned char c:s){if(c=='"'||c=='\\'){r+='\\';r+=c;}else if(c<32){char t[7];snprintf(t,sizeof(t),"\\u%04x",c);r+=t;}else r+=c;}return r+'"';}
public:
 uint32_t active=0;
 static const std::string& Target(){static const std::string path=[](){const char* value=getenv("RE_HYBRID_RESOURCE");std::string s=value?value:"common/splash.group.bin";if(s!="common/environment.group.bin"&&s!="levels/staffarea/staffarea_story.group.bin"&&s!="levels/staffarea/staffarea.luc"&&s!="common/splash.group.bin"&&s!="common/scripts/storymissions.luc"&&s!="levels/vip/vip.group.bin"&&s!="levels/baggage/baggage.group.bin"&&s!="levels/staffarea/staffarea.group.bin")throw std::runtime_error("Resource is outside the experiment allowlist");return s;}();return path;}
 static bool OverrideAllowed(const std::string& path){
  if(path==Target()||path=="common/fixed_wav.group.bin")return true;
  // Explicit source-text corrections for the five supported language files.
  if(path=="localisation/english.dat"||path=="localisation/french.dat"||path=="localisation/german.dat"||path=="localisation/italian.dat"||path=="localisation/spanish.dat")return true;
  if(const char* route=getenv("RE_TEST_ROUTE")){if(std::string(route)!="skip_intro"&&std::string(route)!="staffarea")throw std::runtime_error("Unknown diagnostic route");if(path=="common/scripts/storymode.luc"||(std::string(route)=="staffarea"&&path=="levels/vip/vip.luc"))return true;}
  if(const char* bundle=getenv("RE_HYBRID_BUNDLE")){if(std::string(bundle)!="staffarea")throw std::runtime_error("Unknown restoration bundle");return path=="common/environment.group.bin"||path=="levels/staffarea/staffarea.group.bin"||path=="levels/staffarea/staffarea_story.group.bin"||path=="levels/staffarea/staffarea.luc"||path=="levels/planecargo/planecargo.group.bin"||path=="levels/planecargo/planecargo_story.group.bin"||path=="levels/planecargo/planecargo.luc"||path=="levels/warehouse/warehouse.group.bin"||path=="levels/warehouse/warehouse_story.group.bin"||path=="levels/warehouse/warehouse.luc"||path=="levels/planecrashed/planecrashed.group.bin"||path=="levels/planecrashed/planecrashed_story.group.bin"||path=="levels/planecrashed/planecrashed.luc"||path=="levels/generatortunnels/generatortunnels.group.bin"||path=="levels/generatortunnels/generatortunnels_story.group.bin"||path=="levels/generatortunnels/generatortunnels.luc"||path=="levels/infirmary/infirmary.group.bin"||path=="levels/infirmary/infirmary_story.group.bin"||path=="levels/infirmary/infirmary.luc"||path=="levels/planeexit/planeexit.group.bin"||path=="levels/planeexit/planeexit_story.group.bin"||path=="levels/planeexit/planeexit.luc"||path=="levels/dutyfreewest/dutyfreewest.group.bin"||path=="levels/dutyfreewest/dutyfreewest_story.group.bin"||path=="levels/dutyfreewest/dutyfreewest.luc"||path=="levels/dutyfreeeast/dutyfreeeast.group.bin"||path=="levels/dutyfreeeast/dutyfreeeast_story.group.bin"||path=="levels/dutyfreeeast/dutyfreeeast.luc"||path=="levels/dutyfreeeast/dutyfreeeast_mercenary.group.bin"||path=="levels/dutyfreeeast/dutyfreeeast_mercenary.luc"||path=="levels/vipplane/vipplane.group.bin"||path=="levels/vipplane/vipplane_story.group.bin"||path=="levels/vipplane/vipplane.luc"||path=="levels/security/security.group.bin"||path=="levels/security/security_story.group.bin"||path=="levels/security/security.luc"||path=="levels/planeentrance/planeentrance.group.bin"||path=="levels/planeentrance/planeentrance_story.group.bin"||path=="levels/planeentrance/planeentrance.luc";}
  return false;
 }
 HybridTrace(){if(const char*p=getenv("RE_HYBRID_TRACE")){directory=p;std::filesystem::create_directories(directory);records=fopen((directory+"/events.jsonl").c_str(),"wb");}}
 ~HybridTrace(){for(auto& item:streams)if(item.second.dump)fclose(item.second.dump);if(records)fclose(records);}
 bool Has(uint32_t h)const{return streams.count(h);}
 void Event(uint32_t h,const char* stage,uint32_t pc,uint32_t lr,uint64_t requested=0,uint64_t returned=0,int result=0,const std::string& extra=""){
  auto it=streams.find(h);if(!records||it==streams.end())return;auto&s=it->second;
  fprintf(records,"{\"stage\":%s,\"logical_path\":%s,\"mode\":%s,\"stream\":%u,\"guest_pc\":%u,\"caller_return_pc\":%u,\"offset\":%lld,\"size\":%lld,\"requested\":%llu,\"returned\":%llu,\"result\":%d,\"source_archive\":%s%s}\n",quote(stage).c_str(),quote(Target()).c_str(),quote(s.mode).c_str(),s.id,pc,lr,(long long)s.position,(long long)s.size,(unsigned long long)requested,(unsigned long long)returned,result,s.archive.empty()?"null":quote(s.archive).c_str(),extra.c_str());
 }
 void Open(uint32_t h,bool external,uint32_t pc,uint32_t lr){if(!h||!records)return;Stream s;s.id=++serial;s.mode=external?"external":"original";char name[64];snprintf(name,sizeof(name),"/stream_%04u.bin",s.id);s.dump=fopen((directory+name).c_str(),"w+b");streams[h]=std::move(s);Event(h,"open",pc,lr);}
 void Read(uint32_t h,const std::vector<uint8_t>& bytes,uint64_t requested,uint32_t pc,uint32_t lr,uint32_t destination,uint32_t stack,int64_t capacity){auto it=streams.find(h);if(it==streams.end())return;auto&s=it->second;char extra[256];snprintf(extra,sizeof(extra),",\"crc32\":%lu,\"destination\":%u,\"stack_pointer\":%u,\"allocation_remaining\":%lld",(unsigned long)crc32(0,bytes.data(),bytes.size()),destination,stack,(long long)capacity);Event(h,"read",pc,lr,requested,bytes.size(),0,extra);if(s.dump&&s.position>=0){fseek(s.dump,long(s.position),SEEK_SET);fwrite(bytes.data(),1,bytes.size(),s.dump);}if(s.position>=0)s.position+=bytes.size();}
 void Seek(uint32_t h,int32_t amount,uint32_t origin,uint32_t result,uint32_t pc,uint32_t lr){auto it=streams.find(h);if(it==streams.end())return;char extra[128];snprintf(extra,sizeof(extra),",\"seek_amount\":%d,\"seek_origin\":%u",amount,origin);Event(h,"seek",pc,lr,0,0,result,extra);if(!result){auto&s=it->second;if(origin==0)s.position=amount;else if(origin==1&&s.position>=0)s.position+=amount;else if(origin==2&&s.size>=0)s.position=s.size+amount;else s.position=-1;}}
 void Tell(uint32_t h,uint32_t pos,uint32_t pc,uint32_t lr){auto it=streams.find(h);if(it!=streams.end())it->second.position=pos;Event(h,"tell",pc,lr,0,pos);}
 void Size(uint32_t h,uint32_t size,uint32_t pc,uint32_t lr){auto it=streams.find(h);if(it!=streams.end())it->second.size=size;Event(h,"size",pc,lr,0,size);}
 void Close(uint32_t h,uint32_t result,uint32_t pc,uint32_t lr){Event(h,"close",pc,lr,0,0,result);auto it=streams.find(h);if(it!=streams.end()){if(it->second.dump)fclose(it->second.dump);streams.erase(it);}if(records)fflush(records);}
 void Backend(const std::string& archive,uint64_t offset,uint64_t requested){auto it=streams.find(active);if(it==streams.end()||it->second.mode!="original")return;it->second.archive=archive;Event(active,"archive_read",0,0,requested,0,0,",\"archive_offset\":"+std::to_string(offset));}
 void Decode(uint64_t requested,uint64_t returned,int error,uint32_t pc,uint32_t lr){Event(active,"decode",pc,lr,requested,returned,error);}
};
