#pragma once
#include "cpu.h"
#include <array>
#include <vector>
#include <string>
#include <memory>
#include <functional>
class S3ERuntime {
public:
    using Keys=std::array<bool,256>;
    S3ERuntime(Cpu* cpu,const std::string& assets,const std::string& saves);
    ~S3ERuntime();
    void Init(const std::vector<std::string>& imports,const std::string& config);
    void SetFrameCallback(std::function<void(uint32_t,const uint16_t*,Keys&)> fn);
    void SetPollCallback(std::function<void(Keys&)> fn);
    void SetAudioCallback(std::function<void(const int16_t*,size_t,uint32_t)> fn);
    void SetChannelAudioCallback(std::function<void(uint32_t,const int16_t*,size_t,uint32_t)> fn);
    struct VideoRequest {uint32_t repeat,left,top,width,height,volume;};
    using VideoPlayer=std::function<int(const std::string&,const VideoRequest&)>;
    void SetVideoPlayer(VideoPlayer player);
    void SetExternalMusicCallback(std::function<void(int16_t*,size_t,uint32_t,bool)> fn);
    std::string RaceCity() const;
    uint32_t MasterVolume() const;
    void RequestQuit();
    // Diagnostic: invoke the registered OS-pause callback, then stop execution.
    void RequestSuspendAndStop();
    int Run(uint32_t entry,uint32_t maxFrames=0);
    uint32_t Frames() const;
    unsigned SurfaceWidth() const;
    void RequestDisplayToggle();
    uint32_t TakeConsolePrompts();
    bool Failed() const;
    bool KeypadOpen() const;
    bool QueueKeypadKey(uint32_t key);
    void PrepareStreamChecks(); // desktop-only diagnostic calls after a bounded run
private:
    struct Impl;std::unique_ptr<Impl> p;
};
