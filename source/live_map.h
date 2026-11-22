#pragma once
#include "cpu.h"
#include "loader.h"
#include "map_art.h"
#include "runtime_clock.h"
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>
#include <vector>
#include <zlib.h>
#ifdef __3DS__
#include "gpu_map.h"
#endif

class LiveMap {
    static constexpr int Width=302, Height=174;
    using Vec=std::array<int32_t,3>;
    using Point=std::array<int,2>;
    struct Face { std::array<int16_t,3> vertices, neighbors; };
    struct Room { uint32_t action; std::array<int32_t,6> bounds; bool visited=false; };
    struct Marker { uint32_t entity, component, type; };
    struct Tile { unsigned face,room; };
    struct Key {
        std::string level;
        uint32_t mesh=0,root=0,vertices=0,faces=0,vertexCount=0,faceCount=0;
        bool operator==(const Key& other) const {
            return level==other.level&&mesh==other.mesh&&root==other.root&&
                vertices==other.vertices&&faces==other.faces&&
                vertexCount==other.vertexCount&&faceCount==other.faceCount;
        }
    };
    Cpu& cpu;
    bool supported, open=false, valid=false;
    uint64_t next=0;
    Key cached;
    std::vector<Vec> vertices;
    std::vector<Face> faces;
    std::vector<Room> rooms;
    std::vector<Marker> markers;
    uint64_t nextMarkerScan=0;
    bool previousTreasureEnabled=false;
    std::array<std::vector<Tile>,4> floors;
    static constexpr int PanelWidth=Width+2, PanelHeight=Height+2;
    std::vector<uint16_t> pixels, panel, emptyPanel, unavailablePanel;
    std::vector<Point> projected;
    std::vector<std::array<Point,2>> projectedRooms;
    bool panelsReady=false;
    uint64_t slowestRefresh=0;
    unsigned refreshes=0, gpuRefreshes=0;
    bool dirty=true, suspended=false;
#ifdef __3DS__
    GpuMap gpu;
    bool discardGpu=false, gpuFailed=false;
    struct GpuSprite { Point point; const uint8_t* rgba; int size; };
    std::vector<GpuSprite> gpuSprites;
    bool recordingGpu=false;
#endif

    template<class T> bool Read(uint32_t address,T& out) {
        return address&&cpu.MemRead(address,&out,sizeof(out))==0;
    }
    uint32_t Word(uint32_t address) {
        uint32_t value=0;
        Read(address,value);
        return value;
    }
    static const std::array<int32_t,4>* Heights(const std::string& name) {
        struct Level { const char* name; std::array<int32_t,4> heights; };
        static constexpr Level levels[]={
            {"baggage",{-10,1000,4000,6000}}, {"dutyfreeeast",{-10,1270,1601,6000}},
            {"dutyfreewest",{-10,1270,4000,6000}}, {"generatortunnels",{2000,3000,4000,6000}},
            {"infirmary",{4998,4999,5000,6000}}, {"planecargo",{1000,2000,4000,6000}},
            {"planecrashed",{-100,1270,4000,6000}}, {"planeentrance",{-10,1270,4000,6000}},
            {"planeexit",{-10,1270,4000,6000}}, {"security",{-10,1270,4000,6000}},
            {"staffarea",{0,4000,8000,9000}}, {"vip",{400,2500,4500,6000}},
            {"vipplane",{-10,3000,4000,6000}}, {"warehouse",{-10,3000,4000,6000}}
        };
        for(const auto& level:levels)if(name==level.name)return &level.heights;
        return nullptr;
    }
    bool GetKey(Key& key) {
        const auto state=Word(G(0x4a0fa168));
        const auto context=Word(G(0x4a0fa1b0));
        if(!state||!context)return false;
        char name[33]{};
        if(cpu.MemRead(state+0x50,name,32))return false;
        key.level=name;
        for(char& c:key.level)c=char(std::tolower(static_cast<unsigned char>(c)));
        key.root=Word(context+0x30);
        const auto owner=Word(context+0x24);
        const auto iface=owner?Word(owner+4):0;
        if(iface<20||!key.root)return false;
        key.mesh=iface-20;
        if(Word(key.mesh)!=G(0x4a0f04dc))return false;
        key.faces=Word(key.mesh+0x1c);
        key.faceCount=Word(key.mesh+0x20);
        key.vertices=Word(key.mesh+0x2c);
        key.vertexCount=Word(key.mesh+0x30);
        return key.faces&&key.vertices&&key.faceCount&&key.vertexCount&&
            key.faceCount<=8192&&key.vertexCount<=8192;
    }
    bool Position(uint32_t provider,Vec& out) {
        const auto type=provider?Word(provider):0;
        if(type==G(0x4a0e6094))return Read(provider+0x6c,out);
        if(type==G(0x4a0f4298))return Read(provider+0x38,out);
        return false;
    }
    bool Collect(uint32_t root,bool rebuildRooms) {
        std::vector<Marker> found;
        std::vector<uint32_t> pending{root};
        std::set<uint32_t> nodes,entities;
        while(!pending.empty()){
            const auto node=pending.back();
            pending.pop_back();
            if(!node||!nodes.insert(node).second)continue;
            const auto list=Word(node+12), count=Word(node+16);
            const auto children=Word(node+28), childCount=Word(node+32);
            if(nodes.size()>4096||count>8192||childCount>256||
               (count&&!list)||(childCount&&!children))return false;
            for(unsigned i=0;i<childCount;++i)pending.push_back(Word(children+4*i));
            for(unsigned i=0;i<count;++i){
                const auto link=Word(list+4*i);
                const auto entity=link?Word(link+8):0;
                if(!entity||!entities.insert(entity).second)continue;
                if(entities.size()>8192)return false;
                const auto marker=Word(entity+0x74);
                const auto type=marker?Word(marker):0;
                if(type==G(0x4a0e7ce0)||type==G(0x4a0f1ee8)||
                   type==G(0x4a0ef86c)||type==G(0x4a0e97f8)||type==G(0x4a0ec680))
                    found.push_back({entity,marker,type});
                if(!rebuildRooms)continue;
                const auto action=Word(entity+0x60);
                if(!action||Word(action)!=G(0x4a0e9a74))continue;
                const auto collider=Word(entity+0x30);
                const auto shape=collider?Word(collider+0x14):0;
                if(!shape||Word(shape)!=G(0x4a0e95fc))continue;
                const auto volume=Word(shape+8), provider=Word(shape+0x10);
                Room room{action,{}};
                Vec origin{};
                if(!volume||Word(volume)!=G(0x4a0ea714)||!Position(provider,origin)||
                   !Read(volume+0x1c,room.bounds))continue;
                // These room bounds are already axis-aligned for the guest map.
                // Its original map adds the provider position even when the provider is rotated.
                for(unsigned j=0;j<6;++j)room.bounds[j]+=origin[j%3];
                rooms.push_back(room);
            }
        }
        markers.swap(found);
        return !rooms.empty();
    }
    bool Rebuild(const Key& key,const std::array<int32_t,4>& heights) {
        cached={};
        rooms.clear(); markers.clear();
        for(auto& floor:floors)floor.clear();
        vertices.resize(key.vertexCount); faces.resize(key.faceCount);
        if(cpu.MemRead(key.vertices,vertices.data(),vertices.size()*sizeof(Vec))||
           cpu.MemRead(key.faces,faces.data(),faces.size()*sizeof(Face))||!Collect(key.root,true))return false;
        for(unsigned i=0;i<faces.size();++i){
            const auto& face=faces[i];
            for(auto index:face.vertices)if(index<0||unsigned(index)>=vertices.size())return false;
            Vec lo=vertices[face.vertices[0]], hi=lo;
            for(auto index:face.vertices)for(unsigned axis=0;axis<3;++axis){
                lo[axis]=std::min(lo[axis],vertices[index][axis]);
                hi[axis]=std::max(hi[axis],vertices[index][axis]);
            }
            const auto high=std::lower_bound(heights.begin(),heights.end(),hi[1])-heights.begin();
            const auto low=std::lower_bound(heights.begin(),heights.end(),lo[1])-heights.begin();
            for(unsigned j=0;j<rooms.size();++j){
                const auto& b=rooms[j].bounds;
                // The guest associates rooms with faces in XZ, then assigns each to floor bands.
                if(lo[0]>b[3]||hi[0]<b[0]||lo[2]>b[5]||hi[2]<b[2])continue;
                for(auto slot=low;slot<=high&&slot<4;++slot){
                    if(b[1]<=heights[slot]&&(slot==0||b[4]>=heights[slot-1]))
                        floors[slot].push_back({i,j});
                }
            }
        }
        cached=key;
        std::printf("[LiveMap] %s rooms=%u faces=%u marker candidates=%u\n",key.level.c_str(),
                    unsigned(rooms.size()),unsigned(faces.size()),unsigned(markers.size()));
        return true;
    }
    static Point Project(const Vec& point,const Vec& center) {
        auto axis=[](int32_t a,int32_t b,int half) {
            return int(std::clamp<int64_t>((int64_t(a)-b)*33/1000+half,-32768,32768));
        };
        return {axis(point[0],center[0],Width/2),axis(point[2],center[2],Height/2)};
    }
    void Pixel(int x,int y,uint16_t color) {
        if(unsigned(x)<Width&&unsigned(y)<Height)pixels[y*Width+x]=color;
    }
    void Line(Point a,Point b,uint16_t color,uint16_t visitedColor,Point lo,Point hi) {
#ifdef __3DS__
        if(recordingGpu){
            gpu.Clip(0,0,Width,Height);
            gpu.Line(a[0],a[1],b[0],b[1],color);
            if(visitedColor!=color&&ClipGpu(lo,hi))
                gpu.Line(a[0],a[1],b[0],b[1],visitedColor);
            return;
        }
#endif
        for(unsigned axis=0;axis<2;++axis){
            const int limit=axis==0?Width:Height;
            if(std::max(a[axis],b[axis])<-1||std::min(a[axis],b[axis])>=limit)return;
        }
        int dx=std::abs(a[0]-b[0]), dy=-std::abs(a[1]-b[1]);
        int sx=a[0]<b[0]?1:-1, sy=a[1]<b[1]?1:-1, error=dx+dy;
        for(;;){
            const int x2=a[0]+(dx>=-dy?0:1), y2=a[1]+(dx>=-dy?1:0);
            auto wall=[&](int x,int y) {
                Pixel(x,y,x>=lo[0]&&x<=hi[0]&&y>=lo[1]&&y<=hi[1]?visitedColor:color);
            };
            wall(a[0],a[1]);wall(x2,y2);
            if(a==b)break;
            const int twice=2*error;
            if(twice>=dy){error+=dy;a[0]+=sx;}
            if(twice<=dx){error+=dx;a[1]+=sy;}
        }
    }
#ifdef __3DS__
    bool ClipGpu(Point lo,Point hi) {
        const int left=std::max(0,lo[0]), top=std::max(0,lo[1]);
        const int right=std::min(Width,hi[0]+1), bottom=std::min(Height,hi[1]+1);
        if(left>=right||top>=bottom)return false;
        gpu.Clip(left,top,right,bottom);
        return true;
    }
#endif
    void Triangle(const std::array<Point,3>& p,uint16_t color,Point lo,Point hi) {
#ifdef __3DS__
        if(recordingGpu){
            if(ClipGpu(lo,hi))gpu.Triangle(p[0][0],p[0][1],p[1][0],p[1][1],p[2][0],p[2][1],color);
            return;
        }
#endif
        const int left=std::max({0,lo[0],std::min({p[0][0],p[1][0],p[2][0]})});
        const int right=std::min({Width-1,hi[0],std::max({p[0][0],p[1][0],p[2][0]})});
        const int top=std::max({0,lo[1],std::min({p[0][1],p[1][1],p[2][1]})});
        const int bottom=std::min({Height-1,hi[1],std::max({p[0][1],p[1][1],p[2][1]})});
        if(left>right||top>bottom)return;
        auto cross=[](const Point& a,const Point& b,int x,int y){
            return int64_t(b[0]-a[0])*(y-a[1])-int64_t(b[1]-a[1])*(x-a[0]);
        };
        const auto area=cross(p[0],p[1],p[2][0],p[2][1]);
        if(!area)return;
        const int sign=area>0?1:-1;
        std::array<int,3> dx{},dy{};
        std::array<int64_t,3> values{};
        for(unsigned i=0;i<3;++i){
            const auto& a=p[i];
            const auto& b=p[(i+1)%3];
            dx[i]=sign*(a[1]-b[1]);
            dy[i]=sign*(b[0]-a[0]);
            values[i]=sign*cross(a,b,left,top);
        }
        const int span=right-left;
        for(int y=top;y<=bottom;++y){
            int first=0,last=span;
            for(unsigned i=0;i<3;++i){
                const auto value=values[i];
                values[i]+=dy[i];
                const int step=dx[i];
                const auto end=value+int64_t(step)*span;
                if(value<0&&end<0){last=-1;continue;}
                if(value<0)first=std::max(first,int((-value+step-1)/step));
                else if(end<0)last=std::min(last,int(value/-step));
            }
            if(first<=last)std::fill_n(pixels.data()+y*Width+left+first,last-first+1,color);
        }
    }
    void Sprite(Point center,const uint8_t* rgba,int size) {
#ifdef __3DS__
        if(recordingGpu){gpuSprites.push_back({center,rgba,size});return;}
#endif
        for(int y=0;y<size;++y)for(int x=0;x<size;++x){
            const int px=center[0]+x-size/2, py=center[1]+y-size/2;
            if(unsigned(px)>=Width||unsigned(py)>=Height)continue;
            const auto* p=rgba+4*(y*size+x);
            if(!p[3])continue;
            auto& dst=pixels[py*Width+px];
            dst=Blend(dst?dst:0x1987,p);
        }
    }
    bool TreasureEnabled() {
        const auto manager=Word(G(0x4a0fa144));
        const auto entry=manager?Word(manager+0x28):0;
        const auto info=entry?Word(entry+4):0;
        uint8_t enabled=0;
        return info&&Read(info+4,enabled)&&enabled;
    }
    void RenderFloor(unsigned slot,const Vec& center,const std::array<int32_t,4>& heights,
                     uint32_t playerEntity) {
#ifdef __3DS__
        if(!recordingGpu)
#endif
            pixels.assign(Width*Height,0);
        projectedRooms.resize(rooms.size());
        for(unsigned j=0;j<rooms.size();++j){
            auto& room=rooms[j];
            const auto& b=room.bounds;
            projectedRooms[j]={Project({b[0],0,b[2]},center),Project({b[3],0,b[5]},center)};
            uint8_t flag=0;
            room.visited=Word(room.action)==G(0x4a0e9a74)&&Read(room.action+24,flag)&&flag;
        }
        projected.resize(vertices.size());
        for(unsigned i=0;i<vertices.size();++i)projected[i]=Project(vertices[i],center);
        for(unsigned pass=0;pass<3;++pass)for(const auto& tile:floors[slot]){
            const auto& room=rooms[tile.room];
            if(pass==1&&!room.visited)continue;
            const auto& face=faces[tile.face];
            const std::array<Point,3> p{projected[face.vertices[0]],
                projected[face.vertices[1]],projected[face.vertices[2]]};
            if(std::min({p[0][0],p[1][0],p[2][0]})>=Width||
               std::min({p[0][1],p[1][1],p[2][1]})>=Height||
               std::max({p[0][0],p[1][0],p[2][0]})<-1||
               std::max({p[0][1],p[1][1],p[2][1]})<-1)continue;
            const auto& [lo,hi]=projectedRooms[tile.room];
            if(pass==0)Triangle(p,0x3a4b,{0,0},{Width-1,Height-1});
            else if(pass==1)Triangle(p,0x64b4,lo,hi);
            else for(unsigned i=0;i<3;++i)if(face.neighbors[i]==-1)
                Line(p[i],p[(i+1)%3],0x63ef,room.visited?0x95d8:0x63ef,lo,hi);
        }
        const bool treasureEnabled=TreasureEnabled();
        for(const auto& marker:markers){
            const bool treasure=marker.type==G(0x4a0ec680);
            uint8_t enabled=0;
            if(marker.entity==playerEntity||Word(marker.entity+0x74)!=marker.component||
               Word(marker.component)!=marker.type||
               !(treasure?treasureEnabled:Read(marker.component+24,enabled)&&enabled))continue;
            Vec point{};
            if(!Position(Word(marker.entity+0x1c),point)||
               std::lower_bound(heights.begin(),heights.end(),point[1])-heights.begin()!=int(slot))continue;
            const auto p=Project(point,center);
            if(treasure)Sprite(p,kMapTreasure,12);
            else if(marker.type==G(0x4a0e97f8)){
                const auto action=Word(marker.entity+0x60);
                // The Staff Area merchant has the named entity and image, but no merchant action slot.
                const auto image=Word(marker.component+0x1c);
                const bool merchant=Word(marker.entity+4)==0x839b2a37 ||
                    (image&&Word(image)==G(0x4a0e697c)&&Word(image+4)==0xd53eb560) ||
                    (action&&Word(action)==G(0x4a0eabdc));
                Sprite(p,merchant?kMapMerchant:kMapObjective,12);
            }else{
                const auto door=Word(marker.entity+0x58);
                uint8_t unlocked=0;
                if(door&&marker.type!=G(0x4a0ef86c))Read(door+28,unlocked);
                Sprite(p,unlocked?kMapUnlocked:kMapLocked,10);
            }
        }
        Sprite({Width/2,Height/2},kMapPlayer,12);
    }
    static uint16_t Blend(uint16_t out,const uint8_t* p) {
        const unsigned a=p[3];
        if(a==255)return ((p[0]>>3)<<11)|((p[1]>>2)<<5)|(p[2]>>3);
        const unsigned r=((p[0]*31/255)*a+(out>>11)*(255-a)+127)/255;
        const unsigned g=((p[1]*63/255)*a+((out>>5)&63)*(255-a)+127)/255;
        const unsigned b=((p[2]*31/255)*a+(out&31)*(255-a)+127)/255;
        return (r<<11)|(g<<5)|b;
    }
    static void Blit(uint16_t* screen,const uint8_t* rgba,int left,int top,int w,int h) {
        for(int y=0;y<h;++y)for(int x=0;x<w;++x){
            const auto* p=rgba+4*(y*w+x);
            const unsigned a=p[3];
            if(!a)continue;
            auto& out=screen[(x+left)*240+239-top-y];
            out=Blend(out,p);
        }
    }
    void PreparePanels(const uint16_t* screen) {
        if(panelsReady)return;
        emptyPanel.resize(PanelWidth*PanelHeight);
        unavailablePanel.resize(emptyPanel.size());
        panel.resize(emptyPanel.size());
        for(int x=0;x<PanelWidth;++x)for(int y=0;y<PanelHeight;++y){
            const int art=4*(y*PanelWidth+x);
            const int index=x*PanelHeight+(PanelHeight-1-y);
            const auto background=screen[(x+8)*240+216-y];
            emptyPanel[index]=Blend(background,kMapZone+art);
            unavailablePanel[index]=Blend(emptyPanel[index],kMapUnavailable+art);
        }
        panelsReady=true;
    }
    void ComposePanel() {
        panel=emptyPanel;
        for(int x=0;x<Width;++x)for(int y=0;y<Height;++y)
            if(const auto color=pixels[y*Width+x])
                panel[(x+1)*PanelHeight+Height-y]=color;
    }

public:
    LiveMap(Cpu& cpu,const S3EBinary& binary,bool gpuEnabled=true):cpu(cpu),supported(
        binary.code_and_data.size()==1083816&&
        crc32(0,binary.code_and_data.data(),binary.code_and_data.size())==0xb90753f9)
#ifdef __3DS__
        ,gpu(gpuEnabled)
#endif
    {}
    bool IsOpen() const { return open; }
    void Toggle(){
        open=!open;
        suspended=false;
        Suspend();
        suspended=false;
    }
    void Suspend(){
        if(suspended)return;
        suspended=true;
#ifdef __3DS__
        discardGpu=true;
#endif
        dirty=true;
        valid=false;
    }
    void LogPerformance() const {
#ifdef __3DS__
        if(!gpu.Ready())std::puts("[LiveMap] CPU rasterizer active");
#endif
        std::printf("[LiveMap] CPU refreshes=%u GPU refreshes=%u max CPU preparation=%llu ms\n",
                    refreshes,gpuRefreshes,static_cast<unsigned long long>(slowestRefresh));
    }
    bool Update(uint64_t now) {
        suspended=false;
#ifdef __3DS__
        const uint16_t* image=nullptr;
        int stride=0;
        if(gpu.Take(image,stride)){
            if(!image){
                gpuFailed=true;
                std::puts("[LiveMap] GPU transfer check failed; using CPU fallback");
            }
            if(image&&!discardGpu&&open){
                pixels.resize(Width*Height);
                for(int y=0;y<Height;++y)for(int x=0;x<Width;++x)
                    pixels[y*Width+x]=image[x*stride+Height-1-y];
                for(const auto& sprite:gpuSprites)Sprite(sprite.point,sprite.rgba,sprite.size);
                ComposePanel();
                valid=true;
                dirty=true;
                ++gpuRefreshes;
            }
        }
#endif
        if(!open||!supported||now<next||!panelsReady)return dirty;
        next=now+100;
#ifdef __3DS__
        if(gpu.Pending())return dirty;
#endif
        const auto started=NfsClockMs();
        Key key;
        const auto* heights=GetKey(key)?Heights(key.level):nullptr;
        const auto manager=heights?Word(G(0x4a0fa16c)):0;
        const auto holder=manager?Word(manager+0x1c):0;
        Vec player{};
        const bool newLevel=!(key==cached);
        if(!heights||!holder||!Position(Word(holder+0x1c),player)||
           (newLevel&&!Rebuild(key,*heights))){
            cached={};
            dirty|=valid;
            valid=false;
            return dirty;
        }
        const bool treasures=TreasureEnabled();
        if(newLevel||treasures!=previousTreasureEnabled||now>=nextMarkerScan){
            if(!newLevel)Collect(key.root,false);
            previousTreasureEnabled=treasures;
            nextMarkerScan=now+500;
        }
        const auto floor=std::lower_bound(heights->begin(),heights->end(),player[1])-heights->begin();
        if(floor>=4||floors[floor].empty()){
            dirty|=valid;
            valid=false;
            return dirty;
        }
#ifdef __3DS__
        if(gpu.Ready()&&!gpuFailed){
            if(!gpu.Begin())return dirty;
            gpuSprites.clear();
            discardGpu=false;
            recordingGpu=true;
            RenderFloor(floor,player,*heights,holder);
            recordingGpu=false;
            gpu.End();
        }else
#endif
        {
            RenderFloor(floor,player,*heights,holder);
            ComposePanel();
            valid=true;
            dirty=true;
            ++refreshes;
        }
        slowestRefresh=std::max(slowestRefresh,NfsClockMs()-started);
        return dirty;
    }
    void Draw(uint16_t* screen) {
        dirty=false;
        if(open){
            PreparePanels(screen);
            const auto& image=valid?panel:unavailablePanel;
            for(int x=0;x<PanelWidth;++x)
                std::memcpy(screen+(x+8)*240+41,image.data()+x*PanelHeight,PanelHeight*sizeof(uint16_t));
        }
        Blit(screen,open?kMapClose:kMapOpen,288,212,32,28);
    }
};
