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
#include "bottomscreen.h"

// Leave application memory available for the guest's separately mapped regions.
u32 __stacksize__ = 1024 * 1024;
u32 __ctru_heap_size = 24 * 1024 * 1024;
u32 __ctru_linear_heap_size = 4 * 1024 * 1024;
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
    gfxSetScreenFormat(GFX_TOP, GSP_BGR8_OES);
    consoleInit(GFX_BOTTOM, &console);
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
    puts("Resident Evil Degeneration\nNew 3DS baseline 1.1\n");
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
                runtime.SetFrameCallback([&](uint32_t frame, const uint16_t* pixels,
                                             S3ERuntime::Keys& keys) {
                    u8* screen = gfxGetFramebuffer(GFX_TOP, GFX_LEFT, nullptr, nullptr);
                    const unsigned width=runtime.SurfaceWidth();
                    const unsigned left=(400-width)/2;
                    if(left)memset(screen, 0, 400*240*3);
                    for (int y=0; y<240; ++y) for (unsigned x=0; x<width; ++x) {
                        u16 p = pixels[y*width+x];
                        u8* out = screen+((x+left)*240+239-y)*3;
                        out[0]=(p&31)*255/31; out[1]=((p>>5)&63)*255/63;
                        out[2]=((p>>11)&31)*255/31;
                    }
                    uint32_t prompts=runtime.TakeConsolePrompts();
                    if(runtime.KeypadOpen())prompts=0;
                    bool show=runtime.KeypadOpen()&&touchKeypad.Ready();
                    if(show){bottomArtVisible=true;touchKeypad.Draw(reinterpret_cast<u16*>(gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr)));}
                    else if(bottom.Ready()){
                        bottomArtVisible=true;
                        auto* bottomFb=reinterpret_cast<u16*>(gfxGetFramebuffer(GFX_BOTTOM,GFX_LEFT,nullptr,nullptr));
                        bottom.Draw(bottomFb,prompts);
                        if(!runtime.KeypadOpen())DrawDisplayToggle(bottomFb,width==400);
                    }
                    gfxFlushBuffers(); gfxSwapBuffers(); gspWaitForVBlank();
                });
                result = runtime.Run(G(binary.entry_point));
            }
        }
    }
    ShowLogOnScreen();
    printf("\nRuntime ended: %d\n", result); WaitForExit();
    fflush(stdout); fflush(stderr);
    devoptab_list[STD_OUT] = consoleOutput; devoptab_list[STD_ERR] = consoleOutput;
    if (logFile) fclose(logFile);
    gfxExit(); return result;
}
