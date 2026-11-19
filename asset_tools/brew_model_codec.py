"""Verified software mesh framing; opaque vertex values are retained unchanged."""
import struct
from component_codec import Reader,Writer,Unsupported,u32,array
from group_codec import iw_hash

def read(data):
 r=Reader(data,'ngage');header=r.take(24);count=r.u32()
 if count>128:raise Unsupported('block count')
 blocks=[]
 for _ in range(count):
  kind=r.u32();name=r.u32();first,n,flags=struct.unpack('<HHH',r.take(6));b={'class':kind,'name':name,'first':first,'count':n,'flags':flags}
  if kind==iw_hash('CIwModelBlockVerts'):
   unique=r.u16()
   if unique>n:raise Unsupported('vertex remap count')
   b['unique']=unique;b['values']=r.take(2+unique*6+(n-unique)*2)
  elif kind==iw_hash('CIwModelBlockIndGroups'):
   roles=r.take(4);b['roles']=roles;stride=sum(v<128 for v in roles);b['indices']=r.take(n*stride*2)
  elif kind==iw_hash('CIwModelBlockCols'):
   cr=Reader(u32(kind)+struct.pack('<HHH',first,n,flags)+r.data[r.pos:],'ngage');color=cr.block('CIwModelBlockCols');r.pos+=cr.pos-10;b.update(color)
  elif kind==iw_hash('CIwModelBlockBSP'):
   b['material']=r.u32();b['points']=r.take(r.u16()*2);b['primitives']=[]
   for _ in range(n):
    flags=r.u32();b['primitives'].append({'flags':flags,'indices':r.take(8 if flags&2 else 6),'uvs':r.take(16)})
   b['nodes']=r.array(12);b['links']=r.array(4)
  else:raise Unsupported(f'software block {kind:08x}')
  blocks.append(b)
 if r.u32():raise Unsupported('second inline block array')
 materials=r.array(4)
 if r.pos!=len(data):raise ValueError(f'model tail {len(data)-r.pos}')
 return {'header':header,'blocks':blocks,'materials':materials}
def encode(m):
 out=m['header']+u32(len(m['blocks']))
 for b in m['blocks']:
  out+=u32(b['class'])+u32(b['name'])+struct.pack('<HHH',b['first'],b['count'],b['flags'])
  if b['class']==iw_hash('CIwModelBlockVerts'):out+=struct.pack('<H',b['unique'])+b['values']
  elif b['class']==iw_hash('CIwModelBlockIndGroups'):out+=b['roles']+b['indices']
  elif b['class']==iw_hash('CIwModelBlockCols'):
   encoded=Writer('ngage').block(b);out+=encoded[10:]
  else:
   out+=u32(b['material'])+struct.pack('<H',len(b['points'])//2)+b['points']
   for p in b['primitives']:out+=u32(p['flags'])+p['indices']+p['uvs']
   out+=array(b['nodes'],12)+array(b['links'],4)
 return out+u32(0)+array(m['materials'],4)
