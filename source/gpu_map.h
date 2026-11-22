#pragma once
#include <citro2d.h>
#include <cstdint>
#include <array>

class GpuMap {
    static constexpr unsigned TargetWidth=192, TargetHeight=304;
    static constexpr unsigned Bytes=TargetWidth*TargetHeight*sizeof(uint16_t);
    C3D_RenderTarget* target=nullptr;
    uint16_t* output=nullptr;
    bool c3d=false, c2d=false, pending=false, transferOk=false;
    std::array<int,4> clip{};
    static u32 Color(uint16_t v) {
        return C2D_Color32((v>>11)*255/31,((v>>5)&63)*255/63,(v&31)*255/31,255);
    }
public:
    explicit GpuMap(bool enabled=true) {
        if(!enabled)return;
        c3d=C3D_Init(C3D_DEFAULT_CMDBUF_SIZE);
        if(!c3d)return;
        c2d=C2D_Init(16384);
        if(!c2d)return;
        C2D_Prepare();
        target=C3D_RenderTargetCreate(TargetWidth,TargetHeight,GPU_RB_RGB565,-1);
        output=static_cast<uint16_t*>(linearAlloc(Bytes));
        if(output)GSPGPU_FlushDataCache(output,Bytes);
    }
    ~GpuMap() {
        if(pending&&C3D_FrameBegin(0))C3D_FrameEnd(0);
        if(c2d)C2D_Fini();
        if(target)C3D_RenderTargetDelete(target);
        if(c3d)C3D_Fini();
        if(output)linearFree(output);
    }
    bool Ready() const { return target&&output; }
    bool Pending() const { return pending; }
    bool Begin() {
        if(!Ready()||pending||!C3D_FrameBegin(C3D_FRAME_NONBLOCK))return false;
        C2D_TargetClear(target,0);
        C2D_SceneBegin(target);
        clip={-1,-1,-1,-1};
        return true;
    }
    void Clip(int left,int top,int right,int bottom) {
        const std::array<int,4> bounds{left,top,right,bottom};
        if(bounds==clip)return;
        clip=bounds;
        C2D_Flush();
        // The local map is rotated into the same column order as the LCD buffer.
        C3D_SetScissor(GPU_SCISSOR_NORMAL,174-bottom,left,174-top,right);
    }
    void Triangle(int ax,int ay,int bx,int by,int cx,int cy,uint16_t color) {
        const auto c=Color(color);
        C2D_DrawTriangle(173.5f-ay,303.5f-ax,c,173.5f-by,303.5f-bx,c,173.5f-cy,303.5f-cx,c,0);
    }
    void Line(int ax,int ay,int bx,int by,uint16_t color) {
        if(ax==bx&&ay==by)return;
        const auto c=Color(color);
        C2D_DrawLine(173.5f-ay,303.5f-ax,c,173.5f-by,303.5f-bx,c,2,0);
    }
    void End() {
        C2D_Flush();
        C3D_SetScissor(GPU_SCISSOR_DISABLE,0,0,0,0);
        // A pixel in the padding checks transfer completion and row orientation.
        C2D_DrawRectSolid(182,4,0,4,4,C2D_Color32(255,0,255,255));
        C2D_Flush();
        // Split queues the draw before the transfer. Neither operation outputs to an LCD.
        C3D_FrameSplit(0);
        const auto dim=GX_BUFFER_DIM(TargetWidth,TargetHeight);
        transferOk=R_SUCCEEDED(GX_DisplayTransfer(static_cast<u32*>(target->frameBuf.colorBuf),dim,
            reinterpret_cast<u32*>(output),dim,GX_TRANSFER_IN_FORMAT(GX_TRANSFER_FMT_RGB565)|
            GX_TRANSFER_OUT_FORMAT(GX_TRANSFER_FMT_RGB565)));
        C3D_FrameEnd(0);
        pending=true;
    }
    bool Take(const uint16_t*& data,int& stride) {
        if(!pending||!C3D_FrameBegin(C3D_FRAME_NONBLOCK))return false;
        C3D_FrameEnd(GX_CMDLIST_FLUSH);
        pending=false;
        if(transferOk)GSPGPU_InvalidateDataCache(output,Bytes);
        data=nullptr;
        if(transferOk&&output[(TargetHeight-1-5)*TargetWidth+183]==0xf81f){
            data=output;
            stride=TargetWidth;
        }else if(transferOk&&output[5*TargetWidth+183]==0xf81f){
            data=output+(TargetHeight-1)*TargetWidth;
            stride=-int(TargetWidth);
        }
        return true;
    }
};
