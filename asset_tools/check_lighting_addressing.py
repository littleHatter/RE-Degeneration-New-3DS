"""Check repeat addressing, local placeholder medians and grayscale promotion."""
from pathlib import Path
from types import SimpleNamespace
import argparse,struct,collections,json
from lightmap_bake import LightmapBake
from shared_edge_lighting import SeamPass
from component_codec import encode,read
from group_codec import iw_hash
from check_scene_seams import fixture_mesh,FixtureRotation,entity

def check(report):
 b=LightmapBake.__new__(LightmapBake);b.stats=collections.Counter();b.width=b.height=2;b.pixels=bytes([0,0,0,255,50,50,50,255,150,150,150,255,255,255,255,255]);b.address_mode='repeat'
 assert b.sample(1000,-1000)==b.sample(1000,3096)
 assert b.sample(5096,1000)==b.sample(1000,1000)
 b=LightmapBake.__new__(LightmapBake);b.stats=collections.Counter();b.rows=[];b.address_mode='repeat';b.correspondence=lambda h:(4,{i:{i:1.} for i in range(4)},[],set());b.sample=lambda u,v:(u/10,)*3
 uv=[(-4096,8192),(1000,1000),(2000,2000),(-4096,8192)];c={'model':1,'flags':16,'lightmap_uvs':{'count':4,'data':struct.pack('<8h',*(a for p in uv for a in p))},'colors':{'first':44,'count':4,'colors':b'\xff'*16}}
 assert b.bake(c);assert c['colors']['colors']==bytes([150,150,150,255,100,100,100,255,200,200,200,255,150,150,150,255]);assert b.stats['placeholder_uv_samples_using_instance_median']==2
 a=entity(1,(0,0,0),40);a['components'][0]['colors']['mode']=1;d=entity(2,(100,0,0),200);d['components'][0]['colors']['colors']=bytes([200,100,50,255])*4
 resources=[SimpleNamespace(class_id=iw_hash('CIwEntSpec'),in_group_hash=i+1,body=encode(e,'ngage')) for i,e in enumerate([a,d])];g=SimpleNamespace(resources=lambda:resources);s=SeamPass.__new__(SeamPass);s.meshes={1:fixture_mesh(),2:fixture_mesh()};s.rotation=FixtureRotation();r=s.apply([('fixture',g)],{('fixture','00000001','00000001'),('fixture','00000002','00000002')});assert r['statistics']['grayscale_blocks_promoted_to_RGBA']==1;assert read(resources[0].body,'ngage')[0]['components'][0]['colors']['mode']==0
 result={'negative_and_multi_tile_UV_repeat':'passed','placeholder_vertices_use_same_instance_valid_sample_median':'passed','grayscale_storage_promoted_when_smoothing_adds_RGB':'passed'};report.write_text(json.dumps(result,indent=2)+'\n');print(result)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.report)
