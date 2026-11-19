#pragma once
#include <fstream>
#include <vector>
#include <cstdint>
#include <limits>
// Read a known-length asset with one allocation, avoiding iterator growth peaks.
inline bool ReadAssetExact(const std::string& path,std::vector<uint8_t>& bytes){
    std::ifstream f(path,std::ios::binary|std::ios::ate);
    if(!f)return false;
    const auto end=f.tellg();
    if(end<0||static_cast<uint64_t>(end)>bytes.max_size()||static_cast<uint64_t>(end)>static_cast<uint64_t>(std::numeric_limits<std::streamsize>::max()))return false;
    bytes.resize(static_cast<size_t>(end));f.seekg(0);
    return bool(f)&&(!bytes.size()||bool(f.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()))));
}
