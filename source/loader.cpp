#include "loader.h"
#include <cstdlib>
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <cstring>

namespace { uint32_t g_image_base = STOCK_BASE; }
uint32_t TRAMPOLINE_BASE = STOCK_BASE - TRAMPOLINE_SIZE, FB_BASE = 0x4D000000, STACK_BASE = 0x4C000000, HEAP_BASE = 0x50000000;
uint32_t HEAP_SIZE = 64 * 1024 * 1024;
uint32_t ImageBase() { return g_image_base; }
void SetImageBase(uint32_t base) { g_image_base = base; }

#pragma pack(push, 1)
struct XE3UHeader {
    uint32_t ident;
    uint32_t version;
    uint16_t flags;
    uint16_t arch;
    uint32_t fixupOffset;
    uint32_t fixupSize;
    uint32_t codeOffset;
    uint32_t codeFileSize;
    uint32_t codeMemSize;
    uint32_t sigOffset;
    uint32_t sigSize;
    uint32_t entryOffset;
    uint32_t configOffset;
    uint32_t configSize;
    uint32_t baseAddrOrig;
    uint32_t extraOffset;
    uint32_t extraSize;
};
#pragma pack(pop)

bool LoadS3E(const std::string& filepath, S3EBinary& out_bin) {
    std::ifstream file(std::filesystem::u8path(filepath), std::ios::binary | std::ios::ate);
    if (!file.is_open()) {
        std::cerr << "[Loader] Failed to open file: " << filepath << std::endl;
        return false;
    }

    std::streamsize size = file.tellg();
    file.seekg(0, std::ios::beg);

    std::vector<uint8_t> data(size);
    if (!file.read(reinterpret_cast<char*>(data.data()), size)) {
        std::cerr << "[Loader] Failed to read file data" << std::endl;
        return false;
    }

    if (size < sizeof(XE3UHeader)) {
        std::cerr << "[Loader] File too small for XE3U header" << std::endl;
        return false;
    }

    const auto* hdr = reinterpret_cast<const XE3UHeader*>(data.data());
    if (hdr->ident != 0x55334558) { // "XE3U"
        std::cerr << "[Loader] Invalid magic: 0x" << std::hex << hdr->ident << std::dec << std::endl;
        return false;
    }

    out_bin.version = hdr->version;
    out_bin.base_addr = hdr->baseAddrOrig;
    out_bin.entry_point = hdr->baseAddrOrig + hdr->entryOffset;
    if (hdr->configSize && static_cast<uint64_t>(hdr->configOffset) + hdr->configSize <= size)
        out_bin.config.assign(reinterpret_cast<const char*>(data.data()) + hdr->configOffset, hdr->configSize);

    std::cout << "[Loader] Loaded XE3U Executable:" << std::endl;
    std::cout << "  Version:     v" << ((hdr->version >> 24) & 0xFF) << "."
              << ((hdr->version >> 16) & 0xFF) << "."
              << ((hdr->version >> 8) & 0xFF) << "."
              << (hdr->version & 0xFF) << std::endl;
    std::cout << "  Code size:   " << hdr->codeFileSize << " (mem size: " << hdr->codeMemSize << ")" << std::endl;
    std::cout << "  Base addr:   0x" << std::hex << hdr->baseAddrOrig << std::dec << std::endl;
    std::cout << "  Entry point: 0x" << std::hex << out_bin.entry_point << std::dec << std::endl;

    if (static_cast<uint64_t>(hdr->codeOffset)+hdr->codeFileSize>data.size() || hdr->codeFileSize>hdr->codeMemSize || static_cast<uint64_t>(hdr->fixupOffset)+hdr->fixupSize>data.size()) return false;
    out_bin.code_and_data.assign(hdr->codeMemSize,0);
    memcpy(out_bin.code_and_data.data(),data.data()+hdr->codeOffset,hdr->codeFileSize);
    // Parse length-delimited blocks; do not match MGS-specific block sizes.
    for (uint32_t at=0;at<hdr->fixupSize;) {
        if (at+8>hdr->fixupSize) return false;
        const uint8_t* block=data.data()+hdr->fixupOffset+at;
        uint32_t type,size;memcpy(&type,block,4);memcpy(&size,block+4,4);
        if(size<8 || at+size>hdr->fixupSize) return false;
        const uint8_t* payload=block+8;const uint32_t bytes=size-8;
        if(type==0) {
            if(bytes<2)return false;uint16_t n;memcpy(&n,payload,2);uint32_t pos=2;
            for(uint32_t k=0;k<n;++k){uint32_t end=pos;while(end<bytes&&payload[end])++end;if(end==bytes)return false;out_bin.imports.emplace_back(reinterpret_cast<const char*>(payload+pos),end-pos);pos=end+1;}
        } else if(type==1) {
            if(bytes<4)return false;uint32_t n;memcpy(&n,payload,4);if(4ull+n*4ull>bytes)return false;
            out_bin.relocations.resize(n);memcpy(out_bin.relocations.data(),payload+4,n*4);
        } else if(type==2||type==3||type==4) {
            if(bytes<4)return false;uint32_t n;memcpy(&n,payload,4);if(4ull+n*6ull>bytes)return false;
            auto& fixes=type==2?out_bin.arm_fixups:type==3?out_bin.thumb_fixups:out_bin.pointer_fixups;
            for(uint32_t k=0;k<n;++k){const uint8_t* r=payload+4+k*6;fixes.push_back({static_cast<uint32_t>((r[0]<<16)|(r[3]<<8)|r[2]),static_cast<uint16_t>(r[4]|(r[5]<<8))});}
        }
        at+=size;
    }
    for(const auto* fixes:{&out_bin.arm_fixups,&out_bin.thumb_fixups,&out_bin.pointer_fixups})for(const auto& f:*fixes)if(f.offset+4>hdr->codeFileSize||f.func_idx>=out_bin.imports.size())return false;
    std::cout << "  Relocations: " << out_bin.relocations.size() << " pointers, " << out_bin.arm_fixups.size() << " ARM calls, "
              << out_bin.thumb_fixups.size() << " Thumb calls" << std::endl;
    return true;
}

bool SetupSandbox(Cpu* uc, const S3EBinary& bin, uint32_t base, uint32_t heap_size) {
    // 1. Trampolines + image in one block (the image right after the 64 KB of trampolines), relocated to where
    // it lands: `base` under Unicorn, wherever the host puts it natively.
    uint32_t mem_size = (static_cast<uint32_t>(bin.code_and_data.size()) + 0xFFF) & ~0xFFF;
    const uint64_t block = uc->Reserve(base - TRAMPOLINE_SIZE, TRAMPOLINE_SIZE + mem_size);
    if (!block) {
        std::cerr << "[Sandbox] Failed to map code memory" << std::endl;
        return false;
    }
    TRAMPOLINE_BASE = static_cast<uint32_t>(block);
    base = TRAMPOLINE_BASE + TRAMPOLINE_SIZE;
    const uint32_t BASE_ADDR = base;
    std::vector<uint8_t> image = bin.code_and_data;
    if (base != STOCK_BASE) {
        for (uint32_t off : bin.relocations) {
            if (off + 4 > image.size()) continue;
            uint32_t v;
            memcpy(&v, &image[off], 4);
            v = v - STOCK_BASE + base;
            memcpy(&image[off], &v, 4);
        }
        std::cout << "[Sandbox] Image relocated to 0x" << std::hex << base << std::dec << " (" << bin.relocations.size() << " pointers)" << std::endl;
    }
    uc->MemWrite(BASE_ADDR, image.data(), image.size());

    // 2. Trampolines for the imports (SVC #idx; BX LR under Unicorn)
    for (size_t i = 0; i < bin.imports.size(); ++i)
        uc->WriteTrampoline(TRAMPOLINE_BASE + static_cast<uint32_t>(i * 8), static_cast<uint32_t>(i));

    // 3. Patch ARM BL/B calls (Block 2)
    for (const auto& fx : bin.arm_fixups) {
        uint32_t call_addr = BASE_ADDR + fx.offset;
        uint32_t orig_insn = 0;
        uc->MemRead(call_addr, &orig_insn, 4);
        uint32_t cond_and_opcode = orig_insn & 0xFF000000;
        uint32_t target_addr = TRAMPOLINE_BASE + fx.func_idx * 8;
        int32_t disp = (static_cast<int32_t>(target_addr) - static_cast<int32_t>(call_addr + 8)) / 4;
        uint32_t new_insn = cond_and_opcode | (disp & 0x00FFFFFF);
        uc->MemWrite(call_addr, &new_insn, 4);
    }

    // 4. Patch Thumb BLX calls (Block 3)
    for (const auto& fx : bin.thumb_fixups) {
        uint32_t call_addr = BASE_ADDR + fx.offset;
        uint32_t target_addr = TRAMPOLINE_BASE + fx.func_idx * 8;
        int32_t disp = (static_cast<int32_t>(target_addr & ~3) - static_cast<int32_t>((call_addr + 4) & ~3)) / 2;
        uint16_t w1 = 0xF000 | ((disp >> 11) & 0x7FF);
        uint16_t w2 = 0xE800 | (disp & 0x7FF);
        uint16_t blx[2] = {w1, w2};
        uc->MemWrite(call_addr, blx, sizeof(blx));
    }

    for (const auto& fx : bin.pointer_fixups) {
        const uint32_t target = TRAMPOLINE_BASE + fx.func_idx * 8;
        uc->MemWrite(BASE_ADDR + fx.offset, &target, 4);
    }

    // 5. Map Stack, Framebuffer & Heap
    // Debug (README.md section 7): RE_STACK_BASE / RE_FB_BASE / RE_HEAP_BASE=<hex> place the regions elsewhere under
    // Unicorn, e.g. the 3DS's layout (image 9510000, stack 9800000, framebuffer 9b00000, heap 9d00000).
    auto base_env = [](const char* name, uint32_t def) { const char* v = getenv(name); return v ? static_cast<uint32_t>(strtoul(v, nullptr, 16)) : def; };
    STACK_BASE = base_env("RE_STACK_BASE", STACK_BASE); FB_BASE = base_env("RE_FB_BASE", FB_BASE); HEAP_BASE = base_env("RE_HEAP_BASE", HEAP_BASE);
    STACK_BASE = static_cast<uint32_t>(uc->Reserve(STACK_BASE, STACK_SIZE));
    FB_BASE = static_cast<uint32_t>(uc->Reserve(FB_BASE, FB_SIZE));
    HEAP_SIZE = (uc->IsNative() ? 64u : 128u) * 1024 * 1024;
    if (const char* mb = getenv("RE_HEAP_MB")) HEAP_SIZE = static_cast<uint32_t>((std::max)(16, (std::min)(1024, atoi(mb)))) * 1024 * 1024;
    if (heap_size) HEAP_SIZE = heap_size;
    HEAP_BASE = static_cast<uint32_t>(uc->Reserve(HEAP_BASE, HEAP_SIZE));
    if (!STACK_BASE || !FB_BASE || !HEAP_BASE) {
        std::cerr << "[Sandbox] Failed to map the stack, framebuffer or heap" << std::endl;
        return false;
    }
    SetImageBase(base);

    // Initialize SP & LR
    uint32_t sp = STACK_BASE + STACK_SIZE - 0x100;
    uint32_t lr = 0xDEADBEEF;
    uc->RegWrite(Cpu::REG_SP, &sp);
    uc->RegWrite(Cpu::REG_LR, &lr);

    std::cout << "[Sandbox] Image 0x" << std::hex << base << ", trampolines 0x" << TRAMPOLINE_BASE << ", stack 0x"
              << STACK_BASE << ", framebuffer 0x" << FB_BASE << ", heap 0x" << HEAP_BASE << std::dec << " (" << HEAP_SIZE / (1024 * 1024) << " MB)" << std::endl;
    return true;
}
