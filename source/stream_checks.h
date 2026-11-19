#pragma once
#include "runtime_s3e.h"
#include "loader.h"
#include <algorithm>
#include <fstream>
#include <stdexcept>
inline void CheckHybridStream(Cpu* cpu,S3ERuntime& rt,const S3EBinary& bin,const std::string& output){
 using U=uint32_t;auto need=[](bool ok){if(!ok)throw std::runtime_error("Stream behavior differs from reference");};
 const char* fixture=getenv("RE_STREAM_REFERENCE");need(fixture);std::ifstream input(fixture,std::ios::binary);std::vector<uint8_t> expected((std::istreambuf_iterator<char>(input)),{});need(!expected.empty());
 U scratch=FB_BASE+0x80000;
 auto invoke=[&](const char* name,U a=0,U b=0,U c=0,U d=0){auto it=std::find(bin.imports.begin(),bin.imports.end(),name);need(it!=bin.imports.end());U cpsr=0x10,sp=STACK_BASE+STACK_SIZE-512,lr=scratch+64,args[]={a,b,c,d},zero=0;cpu->RegWrite(Cpu::REG_CPSR,&cpsr);cpu->RegWrite(Cpu::REG_SP,&sp);cpu->RegWrite(Cpu::REG_LR,&lr);cpu->MemWrite(sp,&zero,4);for(int i=0;i<4;++i)cpu->RegWrite(i,&args[i]);need(cpu->Start(TRAMPOLINE_BASE+8*(it-bin.imports.begin()),lr,5000000)==0);U value=0;cpu->RegRead(0,&value);need(!rt.Failed());return value;};
 const std::string path=HybridTrace::Target();cpu->MemWrite(scratch+128,path.c_str(),path.size()+1);const char mode[]="rb";cpu->MemWrite(scratch+512,mode,sizeof(mode));U h=invoke("s3eFileOpen",scratch+128,scratch+512);need(h!=0);need(invoke("s3eFileGetSize",h)==expected.size());
 auto read=[&](U size,U count,U offset,U items){U got=invoke("s3eFileRead",scratch+4096,size,count,h);need(got==items);std::vector<uint8_t> bytes(got*size);cpu->MemRead(scratch+4096,bytes.data(),bytes.size());need(offset+bytes.size()<=expected.size()&&std::equal(bytes.begin(),bytes.end(),expected.begin()+offset));};
 read(1,7,0,7);need(invoke("s3eFileTell",h)==7);need(invoke("s3eFileSeek",h,4,0)==0);read(1,4,4,4);need(invoke("s3eFileSeek",h,U(-2),1)==0);need(invoke("s3eFileTell",h)==6);read(1,3,6,3);
 need(invoke("s3eFileSeek",h,U(-5),2)==0);need(invoke("s3eFileTell",h)==expected.size()-5);read(1,12,expected.size()-5,5);need(invoke("s3eFileEOF",h)!=0);read(1,1,expected.size(),0);need(invoke("s3eFileSeek",h,0,0)==0);read(2,3,0,3);need(invoke("s3eFileClose",h)==0);
 std::ofstream report(output+"/stream_checks.json");report<<"{\"passed\":true,\"size\":"<<expected.size()<<",\"read_count_units\":true,\"seek_set_cur_end\":true,\"tell\":true,\"short_read\":true,\"eof\":true,\"close\":true}\n";fprintf(stdout,"[StreamCheck] PASS size/read/seek/tell/short-read/EOF/close\n");
}
