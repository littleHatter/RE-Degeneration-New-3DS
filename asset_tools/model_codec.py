"""Read-only graphics-model subset; software-model conversion remains unsupported.
Unsupported vertex encodings, block types or inline material arrays are rejected.
"""
import struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re_restore_work/tools'))
from group_codec import iw_hash
from component_codec import Reader,Unsupported,u32,array

def read(data,platform="ios"):
 r=Reader(data,platform);header=r.take(24);count=r.u32()
 if count>128:raise Unsupported('model block count')
 blocks=[]
 for _ in range(count):
  kind=r.u32();name=r.u32();first,n,flags=struct.unpack('<HHH',r.take(6));block={'class':kind,'name':name,'first':first,'count':n,'flags':flags}
  if kind==iw_hash('CIwModelBlockVerts'):
   unique=r.u16();packing=r.u16()
   if unique>n:raise Unsupported(f'vertex dictionary {unique}/{n}')
   block['unique']=unique;block['packing']=packing;block['data']=r.take(unique*6+(n-unique)*2)
  elif kind==iw_hash('CIwModelBlockNorms'):
   block['packing']=r.u16();block['data']=r.take(n*6)
  elif kind==iw_hash('CIwModelBlockCols'):
   cr=Reader(u32(kind)+struct.pack('<HHH',first,n,flags)+r.data[r.pos:],platform);block.update(cr.block('CIwModelBlockCols'));r.pos+=cr.pos-10
  elif kind in [iw_hash('CIwModelBlockGLUVs'),iw_hash('CIwModelBlockGLUVs2')]:block['data']=r.take(n*4)
  elif kind==iw_hash('CIwModelBlockGLTriList'):block['material']=r.u32();block['data']=r.take(n*2);block['parts']=r.take(4)
  else:raise Unsupported(f'model block {kind:08x}')
  blocks.append(block)
 second_count=r.u32()
 if second_count:raise Unsupported('second inline block array')
 materials=r.array(4)
 if r.pos!=len(data):raise ValueError(f'model tail {len(data)-r.pos}')
 return {'header':header,'blocks':blocks,'materials':materials}
def encode(model,software=False):
 header=model['header'];blocks=model['blocks']
 if software:raise Unsupported('software model conversion requires index-group and BSP generation; not implemented')
 out=header+u32(len(blocks))
 for b in blocks:
  out+=u32(b['class'])+u32(b['name'])+struct.pack('<HHH',b['first'],b['count'],b['flags'])
  if b['class']==iw_hash('CIwModelBlockVerts'):out+=struct.pack('<HH',b['unique'],b['packing'])+b['data']
  elif b['class']==iw_hash('CIwModelBlockNorms'):out+=struct.pack('<H',b['packing'])+b['data']
  elif b['class']==iw_hash('CIwModelBlockCols'):
   from component_codec import Writer
   out+=Writer('ios').block(b)[10:]
  elif b['class']==iw_hash('CIwModelBlockGLTriList'):out+=u32(b['material'])+b['data']+b['parts']
  else:out+=b['data']
 return out+u32(0)+array(model['materials'],4)
