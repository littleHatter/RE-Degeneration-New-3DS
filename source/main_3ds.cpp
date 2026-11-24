#include "gl3ds.h"
#include "live_map.h"
#include <3ds.h>
#include <sys/iosupport.h>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include "loader.h"
#include "runtime_s3e.h"
#include "audio_3ds.h"
#include "runtime_clock.h"
#include "touch_keypad.h"
#include "display_toggle_art.h"
#include "renderer_menu_art.h"
#include <zlib.h>
#include "bottomscreen.h"

// Leave application memory available for the guest's separately mapped regions.
u32 __stacksize__ = 1024 * 1024;
u32 __ctru_heap_size = 24 * 1024 * 1024;
// MGSM uses three 2 MiB vertex arenas in addition to texture and command buffers.
u32 __ctru_linear_heap_size = 20 * 1024 * 1024;
extern "C" {
extern char *fake_heap_start, *fake_heap_end;
extern u32 __ctru_heap, __ctru_linear_heap;
void __system_allocateHeaps() {
    if (R_FAILED(svcControlMemory(&__ctru_heap, OS_HEAP_AREA_BEGIN, 0,
        __ctru_heap_size, MEMOP_ALLOC, (MemPerm)(MEMPERM_READ|MEMPERM_WRITE))))
        svcBreak(USERBREAK_PANIC);
    if (R_FAILED(svcControlMemory(&__ctru_linear_heap, 0, 0,
        __ctru_linear_heap_size, MEMOP_ALLOC_LINEAR, (MemPerm)(MEMPERM_READ|MEMPERM_WRITE))))
        svcBreak(USERBREAK_PANIC);
    mappableInit(OS_MAP_AREA_BEGIN, OS_MAP_AREA_END);
    fake_heap_start = (char*)__ctru_heap;
    fake_heap_end = fake_heap_start + __ctru_heap_size;
}
}
namespace {
constexpr const char* ROOT = "sdmc:/3ds/res_degene";
PrintConsole console;
const devoptab_t* consoleOutput;
FILE* logFile;
bool bottomArtVisible=false;
ssize_t LogWrite(struct _reent* r, void* fd, const char* text, size_t length) {
    if (!bottomArtVisible && consoleOutput && consoleOutput->write_r)
        consoleOutput->write_r(r, fd, text, length);
    if (logFile) { fwrite(text, 1, length, logFile); fflush(logFile); }
    return length;
}
devoptab_t logOutput;
void WaitForExit() {
    puts("\nPress B to return.");
    while (aptMainLoop()) {
        hidScanInput();
        if (hidKeysDown() & KEY_B) break;
        gfxFlushBuffers();gspWaitForVBlank();
    }
}
}
extern "C" void ShowLogOnScreen() { gfxSetDoubleBuffering(GFX_BOTTOM,false); console.frameBuffer=reinterpret_cast<u16*>(gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr)); bool was=bottomArtVisible;bottomArtVisible=false;consoleSelect(&console);if(was)consoleClear(); gfxFlushBuffers();gfxScreenSwapBuffers(GFX_BOTTOM,false);gspWaitForVBlank(); }

namespace {
constexpr unsigned kToggleTop=240-kToggleHeight;
void DrawDisplayToggle(u16* screen,bool wide){
    const uint8_t* icon=wide?kSwitchToStandard:kSwitchToWide;
    for(unsigned x=0;x<kToggleWidth;++x)for(unsigned y=0;y<kToggleHeight;++y){
        const auto* pixel=icon+(y*kToggleWidth+x)*4;
        const unsigned alpha=pixel[3];
        if(!alpha)continue;
        auto& out=screen[x*240+239-(kToggleTop+y)];
        const unsigned r=((pixel[0]*31/255)*alpha+(out>>11)*(255-alpha)+127)/255;
        const unsigned g=((pixel[1]*63/255)*alpha+((out>>5)&63)*(255-alpha)+127)/255;
        const unsigned b=((pixel[2]*31/255)*alpha+(out&31)*(255-alpha)+127)/255;
        out=(r<<11)|(g<<5)|b;
    }
}
}
int main() {
    gfxInitDefault(); gfxSet3D(false);
    gfxSetScreenFormat(GFX_TOP, GSP_RGB565_OES);
    consoleInit(GFX_BOTTOM, &console);
    auto* menuScreen=gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr);
    uLongf menuBytes=320*240*sizeof(uint16_t);
    if(uncompress(menuScreen,&menuBytes,kRendererMenuArt,sizeof(kRendererMenuArt))!=Z_OK||
       menuBytes!=320*240*sizeof(uint16_t)){
        puts("Unable to load renderer selection artwork.");
        WaitForExit();
        gfxExit();
        return 1;
    }
    gfxFlushBuffers();
    gfxScreenSwapBuffers(GFX_BOTTOM,false);
    bool selected=false, hardware=false;
    while(aptMainLoop()){
        hidScanInput();
        const auto keys=hidKeysDown();
        if(keys&KEY_B)break;
        if(keys&KEY_TOUCH){
            touchPosition point{};
            hidTouchRead(&point);
            if(point.py>=120&&point.py<240&&point.px<320){
                hardware=point.px>=160;
                selected=true;
                break;
            }
        }
        gspWaitForVBlank();
    }
    if(!selected){gfxExit();return 0;}
    while(aptMainLoop()){
        hidScanInput();
        if(!(hidKeysHeld()&KEY_TOUCH))break;
        gspWaitForVBlank();
    }
    if(!aptMainLoop()){gfxExit();return 0;}
    consoleClear();
    if(hardware){
        gfxSetScreenFormat(GFX_TOP,GSP_BGR8_OES);
        GL3DS::SetStereo(false);
        setenv("RE_HW_PROBE","1",1);
    }else unsetenv("RE_HW_PROBE");
    // Draw complete artwork off-screen; never clear the displayed icon strip.
    gfxSetDoubleBuffering(GFX_BOTTOM,true);
    std::error_code ec;
    std::filesystem::create_directories(ROOT, ec);
    logFile = fopen((std::string(ROOT)+"/res_degene.log").c_str(), "w");
    consoleOutput = devoptab_list[STD_OUT];
    logOutput = *consoleOutput;
    logOutput.name = "res_degene_log"; logOutput.write_r = LogWrite;
    devoptab_list[STD_OUT] = &logOutput; devoptab_list[STD_ERR] = &logOutput;
    setvbuf(stdout, nullptr, _IONBF, 0); setvbuf(stderr, nullptr, _IONBF, 0);
    BottomScreen bottom;
    bottom.LoadLoading(std::string(ROOT)+"/ui/loading.bin");
    if(!bottom.Load(std::string(ROOT)+"/ui/bottomscreen.bin"))puts("[ConsoleUI] artwork missing");
    else {bottomArtVisible=true;bottom.Draw(reinterpret_cast<u16*>(gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr)),0);bottom.DrawLoading(reinterpret_cast<u16*>(gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr)));gfxFlushBuffers();gfxSwapBuffers();gspWaitForVBlank();}
    puts("Resident Evil Degeneration\nNew 3DS v1.3\n");
    printf("[Renderer] %s\n",hardware?"Hardware GLES":"Software");
    printf("Data: %s/game\n", ROOT);
    setenv("RE_HYBRID_RESOURCE", "common/environment.group.bin", 1);
    setenv("RE_HYBRID_BUNDLE", "staffarea", 1);
    unsetenv("RE_TEST_ROUTE");
    setenv("RE_RESOURCE_TRACE", "1", 1);
    bool isNew = false; APT_CheckNew3DS(&isNew);
    int result = 1;
    if (!isNew) puts("This port requires a New Nintendo 3DS.");
    else {
        osSetSpeedupEnable(true);
        const uint64_t before = NfsClockMs();
        svcSleepThread(20000000);
        const uint64_t elapsed = NfsClockMs() - before;
        printf("[3DS] System-tick clock check: %llu ms\n", (unsigned long long)elapsed);
        if (elapsed < 10 || elapsed > 1000) {
            puts("Runtime clock check failed; guest will not run.");
            WaitForExit(); gfxExit(); return 1;
        }
        std::string error;
        auto cpu = Cpu::CreateNative(&error);
        if (!cpu) printf("CPU: %s\n", error.c_str());
        else {
            S3EBinary binary;
            std::string assets = std::string(ROOT)+"/game";
            if (LoadS3E(assets+"/resident_evil.xe3u", binary) &&
                SetupSandbox(cpu.get(), binary, STOCK_BASE, 64u<<20)) {
                S3ERuntime runtime(cpu.get(), assets, std::string(ROOT)+"/user");
                runtime.Init(binary.imports, binary.config);
                Audio3DS audio; audio.Init();
                LiveMap liveMap(*cpu,binary,!hardware);
                if(hardware)puts("[LiveMap] 10 Hz CPU rasterizer selected for hardware renderer");
                TouchKeypad touchKeypad;
                if(!touchKeypad.Load(std::string(ROOT)+"/ui/keypad_ui.bin"))puts("[KeypadUI] artwork missing or invalid; touch UI unavailable");
                else puts("[KeypadUI] artwork ready");
                runtime.SetAudioCallback([&](const int16_t* p, size_t n, uint32_t rate) { audio.Push(p,n,rate); });
                puts("D-pad / Circle Pad: move\nA: confirm / fire\nX: aim / knife action\nB: back / map\nY: reload / L: knife or zoom\nAudio output enabled.");
                runtime.SetPollCallback([&](S3ERuntime::Keys& keys) {
                    keys.fill(false);
                    if (!aptMainLoop()) { runtime.RequestQuit(); return; }
                    hidScanInput(); u32 held = hidKeysHeld();
                    touchPosition point{};if(held&KEY_TOUCH)hidTouchRead(&point);
                    int touchKey=touchKeypad.Update(runtime.KeypadOpen(),held&KEY_TOUCH,point.px,point.py);
                    if(touchKey>=0)runtime.QueueKeypadKey(unsigned(touchKey));
                    if(runtime.Frames()&&bottom.Ready()&&!runtime.KeypadOpen()&&(hidKeysDown()&KEY_TOUCH)
                       &&point.px<kToggleWidth&&point.py>=kToggleTop&&point.py<240)
                        runtime.RequestDisplayToggle();
                    if(runtime.Frames()&&bottom.Ready()&&!runtime.KeypadOpen()&&(hidKeysDown()&KEY_TOUCH)
                       &&point.px>=288&&point.px<320&&point.py>=212&&point.py<240)
                        liveMap.Toggle();
                    // Select intentionally has no action.
                    keys[204] = held & (KEY_DUP|KEY_CPAD_UP);
                    keys[205] = held & (KEY_DDOWN|KEY_CPAD_DOWN);
                    keys[206] = held & (KEY_DLEFT|KEY_CPAD_LEFT);
                    keys[207] = held & (KEY_DRIGHT|KEY_CPAD_RIGHT);
                    keys[208] = held & (KEY_A|KEY_R);
                    keys[13] = held & KEY_Y;
                    keys[77] = held & KEY_L;
                    keys[209] = held & KEY_X;
                    keys[210] = held & (KEY_B|KEY_START);
                });
                uint32_t previousPrompts=UINT32_MAX;
                unsigned previousWidth=0;
                bool previousKeypad=false;
                struct FrameTiming { unsigned count=0, slow=0; uint64_t total=0; };
                FrameTiming timings[2];
                uint64_t lastTop=0;
                bool lastMapOpen=false;
                runtime.SetFrameCallback([&](uint32_t frame, const uint16_t* pixels,
                                             S3ERuntime::Keys& keys) {
                    const unsigned width=runtime.SurfaceWidth();
                    if(!hardware&&pixels){
                        auto* screen=reinterpret_cast<uint16_t*>(gfxGetFramebuffer(GFX_TOP,GFX_LEFT,nullptr,nullptr));
                        const unsigned left=(400-width)/2;
                        for(unsigned x=0;x<left;++x){
                            std::fill_n(screen+x*240,240,0);
                            std::fill_n(screen+(399-x)*240,240,0);
                        }
                        // Tile the RGB565 transpose to keep the guest rows and LCD columns in cache.
                        for(unsigned y=0;y<240;y+=8)for(unsigned x=0;x<width;x+=8)
                            for(unsigned dx=0;dx<8;++dx)for(unsigned dy=0;dy<8;++dy)
                                screen[(x+dx+left)*240+239-y-dy]=pixels[(y+dy)*width+x+dx];
                        GSPGPU_FlushDataCache(screen,400*240*sizeof(uint16_t));
                        gfxScreenSwapBuffers(GFX_TOP,false);
                    }
                    const auto topTime=NfsClockMs();
                    const bool mapOpen=liveMap.IsOpen()&&!runtime.KeypadOpen();
                    if(lastTop&&mapOpen==lastMapOpen){
                        auto& timing=timings[mapOpen];
                        const auto gap=topTime-lastTop;
                        ++timing.count;
                        timing.total+=gap;
                        timing.slow+=gap>=25;
                    }
                    lastTop=topTime;
                    lastMapOpen=mapOpen;

                    const bool keypad=runtime.KeypadOpen();
                    const uint32_t prompts=runtime.TakeConsolePrompts();
                    if(keypad)liveMap.Suspend();
                    const bool mapChanged=!keypad&&bottom.Ready()&&liveMap.Update(NfsClockMs());
                    if(keypad||keypad!=previousKeypad||prompts!=previousPrompts||width!=previousWidth||mapChanged){
                        auto* bottomFb=reinterpret_cast<uint16_t*>(
                            gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr));
                        if(keypad&&touchKeypad.Ready()){
                            bottomArtVisible=true;
                            touchKeypad.Draw(bottomFb);
                        }else if(bottom.Ready()){
                            bottomArtVisible=true;
                            bottom.Draw(bottomFb,keypad?0:prompts);
                            if(!keypad){
                                DrawDisplayToggle(bottomFb,width==400);
                                liveMap.Draw(bottomFb);
                            }
                        }
                        if(bottomArtVisible){
                            GSPGPU_FlushDataCache(bottomFb,320*240*sizeof(uint16_t));
                            gfxScreenSwapBuffers(GFX_BOTTOM,false);
                        }
                        previousKeypad=keypad;
                        previousPrompts=prompts;
                        previousWidth=width;
                    }
                    if(!hardware)gspWaitForVBlank();
                });
                result = runtime.Run(G(binary.entry_point));
                if(hardware)GL3DS::Shutdown();
                liveMap.LogPerformance();
                for(unsigned i=0;i<2;++i){
                    const auto& timing=timings[i];
                    if(timing.count)std::printf("[Timing] map %s: %u frames, %u gaps >=25 ms, %.2f ms mean\n",
                        i?"open":"closed",timing.count,timing.slow,double(timing.total)/timing.count);
                }
            }
        }
    }
    if (result != 0) {
        ShowLogOnScreen();
        printf("\nRuntime ended: %d\n", result);
        WaitForExit();
    }
    fflush(stdout); fflush(stderr);
    devoptab_list[STD_OUT] = consoleOutput; devoptab_list[STD_ERR] = consoleOutput;
    if (logFile) fclose(logFile);
    gfxExit(); return result;
}
