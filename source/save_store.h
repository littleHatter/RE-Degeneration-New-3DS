#pragma once
#include <cstdio>
#include <cerrno>
#include <cstdint>
#include <string>
#include <vector>
#include <sys/stat.h>

// Keep the prior save recoverable, without requiring rename-over-existing
// support from the SD filesystem. The optional rename function supports a
// regression test with FAT-style destination-exists behavior.
class SaveStore {
public:
    using Rename=int(*)(const char*,const char*);
    explicit SaveStore(std::string directory,Rename renameFn=std::rename):root(std::move(directory)),renameFile(renameFn){}
    unsigned Read(std::vector<char>& bytes,size_t expected){
        std::string path=root+"/saveblob.bin";FILE* f=std::fopen(path.c_str(),"rb");int openError=errno;
        if(!f&&openError==ENOENT){path=root+"/saveblob.bak";f=std::fopen(path.c_str(),"rb");openError=errno;if(f)std::fprintf(stdout,"[Save] Recovering previous save from backup\n");}
        if(!f){std::fprintf(stdout,"[Save] Read failed errno=%d\n",openError);return openError==ENOENT?4:1;}
        bytes.resize(expected);size_t got=std::fread(bytes.data(),1,expected,f);int extra=std::fgetc(f);bool ok=got==expected&&extra==EOF&&!std::ferror(f);std::fclose(f);
        if(!ok){std::fprintf(stdout,"[Save] Invalid size/read: got=%u expected=%u\n",(unsigned)got,(unsigned)expected);return 1;}
        std::fprintf(stdout,"[Save] Read %u bytes\n",(unsigned)expected);return 0;
    }
    bool Write(const std::vector<char>& bytes){
        if(::mkdir(root.c_str(),0777)!=0&&errno!=EEXIST){std::fprintf(stdout,"[Save] mkdir failed errno=%d path=%s\n",errno,root.c_str());return false;}
        std::string path=root+"/saveblob.bin",temp=root+"/saveblob.tmp",backup=root+"/saveblob.bak";
        FILE* f=std::fopen(temp.c_str(),"wb");if(!f){std::fprintf(stdout,"[Save] Temp open failed errno=%d\n",errno);return false;}
        bool ok=std::fwrite(bytes.data(),1,bytes.size(),f)==bytes.size();if(std::fflush(f)!=0)ok=false;if(std::fclose(f)!=0)ok=false;
        if(!ok){std::fprintf(stdout,"[Save] Temp write/close failed errno=%d\n",errno);return false;}
        struct stat info{};bool hadSave=::stat(path.c_str(),&info)==0;
        if(hadSave){
            if(std::remove(backup.c_str())!=0&&errno!=ENOENT){std::fprintf(stdout,"[Save] Old backup removal failed errno=%d\n",errno);return false;}
            if(renameFile(path.c_str(),backup.c_str())!=0){std::fprintf(stdout,"[Save] Backup rename failed errno=%d\n",errno);return false;}
        }
        if(renameFile(temp.c_str(),path.c_str())!=0){
            int installError=errno;bool restored=!hadSave||renameFile(backup.c_str(),path.c_str())==0;
            std::fprintf(stdout,"[Save] Install rename failed errno=%d; prior save restored=%u\n",installError,restored?1:0);return false;
        }
        std::fprintf(stdout,"[Save] Wrote %u bytes; previous-save backup=%u\n",(unsigned)bytes.size(),hadSave?1:0);return true;
    }
private:
    std::string root;Rename renameFile;
};
