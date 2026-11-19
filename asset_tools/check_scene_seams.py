"""Behavior checks for smooth joins, preserved discontinuities and engine rotations."""
from pathlib import Path
import argparse,struct,json,collections
from types import SimpleNamespace
from group_codec import iw_hash
from component_codec import encode,read
from software_model_codec import encode as mesh_encode,read as mesh_read
from shared_edge_lighting import SeamPass
from engine_rotation import EngineRotation,IDENTITY,rotate
U=lambda v:struct.pack('<I',v)

def fixture_mesh(material=1):
 verts={'class':iw_hash('CIwModelBlockVerts'),'name':0,'first':0,'count':4,'flags':0,'unique':4,'values':b'\0\0'+struct.pack('<12h',0,100,0,100,0,0,100,100,0,0,0,0)}
 inds={'class':iw_hash('CIwModelBlockIndGroups'),'name':0,'first':0,'count':4,'flags':0,'roles':bytes([0,255,1]),'indices':struct.pack('<8H',0,0,1,1,2,2,3,3)}
 bsp={'class':iw_hash('CIwModelBlockBSP'),'name':0,'first':0,'count':1,'flags':0,'material':0,'points':b'','primitives':[{'flags':2,'indices':struct.pack('<4H',0,1,2,3),'uvs':b'\0'*16}],'nodes':b'','links':b''}
 return mesh_encode({'header':b'\0'*24,'blocks':[verts,inds,bsp],'materials':U(material)})
class FixtureRotation:
 def matrix(self,q):return IDENTITY if q[-1]==0 else ((0.,0.,-1.),(0.,1.,0.),(1.,0.,0.))

def entity(model,pos,color,rotation=0):
 c={'class':iw_hash('CIwRenderableModelSpec'),'volume':{'class':0},'base':b'\0'*8,'flags':2,'model':model,'materials':b'','colors':{'class':iw_hash('CIwModelBlockCols'),'first':0,'count':4,'flags':0,'mode':0,'colors':bytes([color,color,color,255])*4}}
 return {'flags':0,'components':[c],'position':struct.pack('<3i',*pos),'quaternion':b'\0\0\0@'+bytes([rotation]),'scale':struct.pack('<3i',4096,4096,4096),'ids':b'\0'*8,'active':0,'extra':b''}
def run_case(position=(100,0,0),rotation=0,material=1):
 resources=[SimpleNamespace(class_id=iw_hash('CIwEntSpec'),in_group_hash=i+1,body=encode(e,'ngage')) for i,e in enumerate([entity(1,(0,0,0),40),entity(2,position,200,rotation)])]
 seam=SeamPass.__new__(SeamPass);seam.meshes={1:fixture_mesh(),2:fixture_mesh(material)};seam.rotation=FixtureRotation();group=SimpleNamespace(resources=lambda:resources);eligible={('fixture',f'{i+1:08x}',f'{i+1:08x}') for i in range(2)};result=seam.apply([('fixture',group)],eligible)
 return result,resources,seam,group,eligible

def check(executable,report):
 joined,r,seam,g,eligible=run_case();assert joined['matched_edge_pairs']==1 and joined['changed_color_slots']==4 and joined['cross_instance_edge_pairs']==1
 a=read(r[0].body,'ngage')[0]['components'][0]['colors']['colors'];b=read(r[1].body,'ngage')[0]['components'][0]['colors']['colors']
 assert a[4:8]==b[:4]==bytes([120,120,120,255]);assert a[:4]==bytes([40,40,40,255]) and b[4:8]==bytes([200,200,200,255])
 assert seam.apply([('fixture',g)],eligible)['changed_color_slots']==0
 for kwargs in [{'rotation':1},{'position':(105,0,0)},{'position':(0,0,0)},{'material':2}]:assert run_case(**kwargs)[0]['matched_edge_pairs']==0
 engine=EngineRotation(executable);matrices=[]
 for i in range(24):
  m=engine.matrix(b'\0\0\0@'+bytes([i]));matrices.append(m)
  assert all(abs(sum(m[r][k]*m[s][k] for k in range(3))-(1 if r==s else 0))<1e-9 for r in range(3) for s in range(3))
  det=sum(m[0][i]*(m[1][(i+1)%3]*m[2][(i+2)%3]-m[1][(i+2)%3]*m[2][(i+1)%3]) for i in range(3));assert det==1
 assert len({str(m) for m in matrices})==24 and matrices[0]==IDENTITY
 q=struct.pack('<4i',1<<29,1<<29,1<<29,1<<29);assert rotate((1,0,0),engine.matrix(q))==(0.,1.,0.)
 result={'synthetic_checks':['shared edge corner equality','unshared corners unchanged','idempotent second pass','sharp crease excluded','disconnected gap excluded','overlapping face excluded','different material excluded'],'engine_rotation_checks':'24 unique orthonormal compact matrices; identity and explicit cyclic quaternion checked','joined_fixture':joined}
 report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='joined_fixture'},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.executable,a.report)
