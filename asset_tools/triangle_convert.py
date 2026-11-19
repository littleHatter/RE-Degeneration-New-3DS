"""Bounded triangle conversion for three missing static environment models.
Native controls establish reversed winding, triangle UV ordering and leaf size.
Normals are omitted only for the observed model with explicit baked colors.
"""
import struct,copy
from group_codec import iw_hash
from component_codec import Unsupported,u32
from model_codec import read as glread
from software_model_codec import read as swread,encode

MODEL_IDS={0x06ea0764,0xbd964f5e,0x9ae20780}
def convert(body,material_flags):
 m=glread(body);by={}
 allowed={iw_hash(s) for s in ['CIwModelBlockVerts','CIwModelBlockGLUVs','CIwModelBlockGLUVs2','CIwModelBlockGLTriList','CIwModelBlockCols','CIwModelBlockNorms']}
 if any(b['class'] not in allowed for b in m['blocks']):raise Unsupported('triangle block profile')
 for b in m['blocks']:by.setdefault(b['class'],[]).append(b)
 def single(name):
  values=by.get(iw_hash(name),[])
  if len(values)!=1:raise Unsupported('triangle single block '+name)
  return values[0]
 v=single('CIwModelBlockVerts');uv=single('CIwModelBlockGLUVs');n=v['count']
 if uv['count']!=n or len(material_flags)!=len(m['materials'])//4:raise Unsupported('triangle vertex/material contract')
 if by.get(iw_hash('CIwModelBlockNorms')) and not by.get(iw_hash('CIwModelBlockCols')):raise Unsupported('normals need baked colors')
 vb={k:v[k] for k in ['class','name','first','count','flags','unique']};vb['values']=struct.pack('<H',v['packing'])+v['data']
 ig={'class':iw_hash('CIwModelBlockIndGroups'),'name':iw_hash('CIwModelBlockIndGroups'),'first':0,'count':n,'flags':0,'roles':bytes([0,255,1]),'indices':struct.pack('<'+'H'*(n*2),*(x for i in range(n) for x in (i,i)))}
 blocks=[vb,ig]
 for c in by.get(iw_hash('CIwModelBlockCols'),[]):
  if c['count']!=n:raise Unsupported('model color count')
  blocks.append(copy.deepcopy(c))
 coords=struct.unpack('<'+'h'*(len(uv['data'])//2),uv['data'])
 triangles={}
 for t in by.get(iw_hash('CIwModelBlockGLTriList'),[]):
  if t['count']%3 or t['material']>=len(material_flags):raise Unsupported('triangle index profile')
  ids=struct.unpack('<'+'H'*t['count'],t['data'])
  if any(i>=n for i in ids):raise ValueError('triangle index bounds')
  triangles.setdefault(t['material'],[]).extend(ids[i:i+3] for i in range(0,len(ids),3))
 for material,ts in triangles.items():
  if material_flags[material] not in [0x50001,0x50000]:raise Unsupported('triangle material profile')
  primitives=[];points=[]
  for a,b,c in ts:
   order=(a,c,b)
   points.extend(order)
   uvpairs=[coords[i*2:i*2+2] for i in (a,b,c)]+[(0,0)]
   primitives.append({'flags':0x10c,'indices':struct.pack('<3H',*order),'uvs':struct.pack('<8h',*(v for pair in uvpairs for v in pair))})
  points=list(dict.fromkeys(points));count=len(primitives)
  if not count or 28*(count+1)>65535:raise Unsupported('triangle leaf size')
  blocks.append({'class':iw_hash('CIwModelBlockBSP'),'name':iw_hash('CIwModelBlockBSP'),'first':28*(count+1),'count':count,'flags':0,'material':material,'points':struct.pack('<'+'H'*len(points),*points),'primitives':primitives,'nodes':b'','links':u32(count<<16)})
 if struct.unpack_from('<I',m['header'])[0] not in [0,0x1000000]:raise Unsupported('triangle model flags')
 target={'header':u32(0x80000)+m['header'][4:],'blocks':blocks,'materials':m['materials']}
 out=encode(target);assert encode(swread(out))==out
 return out
