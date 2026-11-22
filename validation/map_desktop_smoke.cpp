#include "live_map.h"
#include <array>
#include <cassert>
#include <cstdio>
int main(int argc,char** argv) {
    assert(argc==2);
    auto cpu=Cpu::CreateUnicorn(nullptr);
    assert(cpu);
    S3EBinary binary{};
    assert(LoadS3E(argv[1],binary));
    assert(SetupSandbox(cpu.get(),binary,STOCK_BASE,64u<<20));
    LiveMap map(*cpu,binary);
    using Screen=std::array<uint16_t,320*240>;
    Screen closed{}, unavailable{}, reclosed{};
    map.Draw(closed.data());
    map.Toggle();
    map.Draw(unavailable.data());
    map.Toggle();
    map.Draw(reclosed.data());
    assert(closed==reclosed);
    size_t buttonChanges=0, viewportChanges=0;
    for(int x=0;x<320;++x)for(int y=0;y<240;++y){
        if(closed[x*240+239-y]==unavailable[x*240+239-y])continue;
        if(x>=288&&y>=212)++buttonChanges;
        else if(x>=8&&x<312&&y>=23&&y<199)++viewportChanges;
        else assert(false);
    }
    assert(buttonChanges>0&&viewportChanges>30000);
    std::printf("PASS closed -> unavailable -> closed: %zu button pixels and %zu viewport pixels changed\n",
                buttonChanges,viewportChanges);

    // Install a minimal Staff Area floor into the sandbox to exercise the real capture path.
    const auto put=[&](uint32_t address,const auto& value){
        assert(cpu->MemWrite(address,&value,sizeof(value))==0);
    };
    const uint32_t base=0x50010000;
    std::array<uint32_t,14> object{};
    for(unsigned i=0;i<object.size();++i)object[i]=base+0x100*i;
    const auto [state,context,owner,mesh,root,list,link,entity,action,collider,shape,volume,provider,player]=object;
    put(G(0x4a0fa168),state);
    put(G(0x4a0fa1b0),context);
    put(G(0x4a0fa16c),player);
    put(state+0x50,"staffarea");
    put(context+0x24,owner); put(context+0x30,root);
    put(owner+4,mesh+20); put(mesh,G(0x4a0f04dc));
    const uint32_t vertices=base+0xe00, faces=base+0xf00;
    put(mesh+0x1c,faces); put(mesh+0x20,1u);
    put(mesh+0x2c,vertices); put(mesh+0x30,3u);
    put(vertices,std::array<int32_t,9>{-1000,0,-1000,1000,0,-1000,0,0,1000});
    put(faces,std::array<int16_t,6>{0,1,2,-1,-1,-1});
    put(root+12,list); put(root+16,1u); put(list,link); put(link+8,entity);
    put(entity+0x60,action); put(action,G(0x4a0e9a74));
    put(entity+0x30,collider); put(collider+0x14,shape); put(shape,G(0x4a0e95fc));
    put(shape+8,volume); put(shape+0x10,provider); put(volume,G(0x4a0ea714));
    put(volume+0x1c,std::array<int32_t,6>{-2000,-100,-2000,2000,100,2000});
    put(provider,G(0x4a0e6094)); put(provider+0x6c,std::array<int32_t,3>{});
    put(player+0x1c,entity); put(entity+0x1c,provider);

    Screen ready{}, persisted{}, shifted{};
    map.Toggle();
    map.Draw(ready.data());
    assert(map.Update(10));
    map.Draw(ready.data());
    assert(ready!=unavailable);
    put(provider+0x6c,std::array<int32_t,3>{500,0,0});
    assert(!map.Update(109));
    map.Draw(persisted.data());
    assert(ready==persisted);
    assert(map.Update(110));
    map.Draw(shifted.data());
    assert(shifted!=ready&&shifted!=unavailable);
    std::puts("PASS moved player retains the old panel before 100 ms and updates it at 100 ms");
    // Simulate the scene registering the merchant after the first map capture.
    const uint32_t merchant=base+0x1000, merchantLink=base+0x1100, merchantIcon=base+0x1200;
    put(list+4,merchantLink); put(merchantLink+8,merchant); put(root+16,2u);
    const uint32_t merchantProvider=base+0x1a00;
    put(merchantProvider,G(0x4a0e6094));
    put(merchantProvider+0x6c,std::array<int32_t,3>{-700,0,0});
    put(merchant+4,0x839b2a37u); put(merchant+0x1c,merchantProvider); put(merchant+0x74,merchantIcon);
    put(merchantIcon,G(0x4a0e97f8)); put(merchantIcon+24,uint8_t(1));
    const auto render=[&](uint64_t tick){
        Screen fresh{};
        map.Update(tick);
        map.Draw(fresh.data());
        return fresh;
    };
    const auto beforeMerchant=render(210);
    assert(beforeMerchant==shifted);
    const auto afterMerchant=render(510);
    assert(afterMerchant!=beforeMerchant);

    // Treasure registration and purchase can happen together between captures.
    const uint32_t treasure=base+0x1300, treasureLink=base+0x1400, treasureIcon=base+0x1500;
    const uint32_t manager=base+0x1600, entry=base+0x1700, info=base+0x1800;
    const uint32_t treasureProvider=base+0x1900;
    put(list+8,treasureLink); put(treasureLink+8,treasure); put(root+16,3u);
    put(treasure+0x1c,treasureProvider); put(treasure+0x74,treasureIcon);
    put(treasureIcon,G(0x4a0ec680)); put(treasureProvider,G(0x4a0e6094));
    put(treasureProvider+0x6c,std::array<int32_t,3>{1700,0,0});
    put(G(0x4a0fa144),manager); put(manager+0x28,entry); put(entry+4,info);
    assert(render(610)==afterMerchant);
    put(info+4,uint8_t(1));
    const auto revealed=render(710);
    assert(revealed!=afterMerchant);
    put(info+4,uint8_t(0));
    assert(render(810)==afterMerchant);
    std::puts("PASS late merchant registration and treasure reveal refresh without a level or save reload");
}
