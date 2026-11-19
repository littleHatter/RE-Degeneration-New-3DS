"""Typed, bounds-checked entity reader for the observed iOS/N-Gage layouts.
No scan-and-delete or guessed object boundaries. Unsupported branches stop conversion.
"""
import struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re_restore_work/tools'))
from group_codec import iw_hash
class Unsupported(ValueError):pass
class Reader:
 def __init__(self,data,platform):self.data=data;self.pos=0;self.platform=platform;self.events=[]
 def take(self,n):
  if n<0 or self.pos+n>len(self.data):raise ValueError(f'truncated field at {self.pos}, need {n}')
  b=self.data[self.pos:self.pos+n];self.pos+=n;return b
 def u8(self):return self.take(1)[0]
 def u16(self):return struct.unpack('<H',self.take(2))[0]
 def u32(self):return struct.unpack('<I',self.take(4))[0]
 def array(self,size):
  count=self.u32()
  if count>65536:raise ValueError('array count too large')
  return self.take(count*size)
 def string(self):
  # Not used until the exact string serializer has been established.
  raise Unsupported('string serializer')
 def volume(self):
  kind=self.u32()
  if kind==0:return {'class':0}
  if kind==iw_hash('CIwVolumeAABox'):return {'class':kind,'name':self.u32(),'bounds':self.take(24)}
  if kind==iw_hash('CIwVolumeCylinder'):return {'class':kind,'name':self.u32(),'cylinder':self.take(20)}
  raise Unsupported(f'volume {kind:08x}')
 def block(self,expected):
  kind=self.u32()
  if kind!=iw_hash(expected):raise Unsupported(f'expected {expected}, got {kind:08x} at {self.pos-4}')
  first,count,flags=struct.unpack('<HHH',self.take(6));result={'class':kind,'first':first,'count':count,'flags':flags}
  if expected in ['CIwModelBlockGLUVs','CIwModelBlockGLUVs2']:result['data']=self.take(count*4)
  elif expected=='CIwModelBlockCols':
   mode=self.u8()
   if mode&~7:raise Unsupported(f'colour encoding {mode}')
   if mode&1:
    data=self.take(count);colors=bytes(c for v in data for c in (v,v,v,255))
   elif mode&4:
    if self.platform=='ngage':raise Unsupported('packed color branch in old SDK')
    result_colors=bytearray()
    for _ in range(count):
     v=self.u16();alpha=self.u8() if mode&2 else 255
     result_colors+=bytes(((v&31)<<3,((v>>5)&63)<<2,((v>>11)&31)<<3,alpha))
    colors=bytes(result_colors)
   else:
    # SDK color arrays store complete R/G/B/A planes, not RGBA tuples.
    planar=self.take(count*4)
    colors=bytes(planar[ch*count+i] for i in range(count) for ch in range(4))
   result['mode']=mode;result['colors']=colors
  else:raise Unsupported(expected)
  return result
 def component(self,depth=0):
  if depth>32:raise Unsupported('nested entity depth')
  start=self.pos;kind=self.u32();result={'class':kind}
  if kind==iw_hash('CIwEntSpec'):result['name']=self.u32();result['entity']=self.entity(depth+1)
  elif kind==iw_hash('CIwRenderableModelSpec'):
   result['volume']=self.volume();result['base']=self.take(8);flags=self.u8();result['flags']=flags
   if flags&~0x1a:raise Unsupported(f'model flags {flags:02x}')
   result['model']=self.u32()
   if flags&8:raise Unsupported('inline material array')
   result['materials']=self.array(4)
   if flags&2:result['colors']=self.block('CIwModelBlockCols')
   if flags&0x10:
    if self.platform=='ngage':raise Unsupported('new UV component in old SDK')
    result['lightmap_uvs']=self.block('CIwModelBlockGLUVs2')
  elif kind==iw_hash('CIwColliderSpec'):
   result['volume']=self.volume();result['data']=self.take(9)
  elif kind in [iw_hash(s) for s in ['CTriggerVolumeSpec','CTriggerInteractableSpec','CDoorSpec','CWindowSpec','CTriggerSecurityKeypadSpec']]:
   result['flags']=self.u8();result['references']=self.array(4)
   # IwSerialiseStringID: serialized u32 hash in these SDK versions.
   result['string_id']=self.u32();result['extra']=self.u32()
   if kind!=iw_hash('CTriggerVolumeSpec'):result['interact']=self.take(16)
   if kind==iw_hash('CDoorSpec'):result['door']=self.take(16)
   if kind==iw_hash('CWindowSpec'):result['window']=self.take(20)
   if kind==iw_hash('CTriggerSecurityKeypadSpec'):
    result['keypad_label']=self.take(5)
    if result['keypad_label'][-1]!=0 or not result['keypad_label'][:4].isdigit():raise Unsupported('unobserved keypad label profile')
  elif kind in [iw_hash(s) for s in ['CActionScriptableSpec','CActionMerchantSpec','CActionInvisibleSpec','CActionCrowSpec','CMapIconDoorSpec','CMapIconDoorShutterSpec']]:pass
  elif kind==iw_hash('CRouteShortcutSpec'):
   result['route_profile']=self.u32()
   if result['route_profile']!=1:raise Unsupported('unobserved route-shortcut profile')
   result['route_endpoints']=self.take(24);result['route_flag']=self.u8()
   if result['route_flag']>1:raise Unsupported('unobserved route-shortcut flag')
  elif kind==iw_hash('CActionMessageSpec'):result['message_id']=self.u32()
  elif kind==iw_hash('CActionExploreSpec'):result['data']=self.take(8)
  elif kind==iw_hash('CHealthSpec'):result['data']=self.take(5)
  elif kind==iw_hash('CAnimatorCutsceneSpec'):result['data']=self.take(1)
  elif kind==iw_hash('CMapIconImageSpec'):result['data']=self.take(6)
  elif kind==iw_hash('CActionChangeLevelSpec'):
   start=self.pos
   while self.u8():
    if self.pos-start>=32:raise ValueError('unterminated change-level name')
   result['target']=self.data[start:self.pos];result['data']=self.take(4)
  else:raise Unsupported(f'component {kind:08x} at {start}')
  self.events.append({'class':kind,'offset':start,'bytes':self.pos-start});return result
 def entity(self,depth=0):
  start=self.pos;flags=self.u8();count=self.u32()
  if flags>count or count>256:raise Unsupported(f'entity flags/count {flags}/{count} at {start}')
  components=[{'reference':self.u32()} if i<flags else self.component(depth) for i in range(count)]
  position=self.take(12);q=self.take(4)
  quaternion=q+self.take(1 if struct.unpack('<I',q)[0]==0x40000000 else 12)
  scale=self.take(12) if self.platform=='ios' else struct.pack('<3i',4096,4096,4096)
  ids=self.take(8);active=self.u8();extra=self.array(4) if self.platform=='ios' else b''
  return {'flags':flags,'components':components,'position':position,'quaternion':quaternion,'scale':scale,'ids':ids,'active':active,'extra':extra}
def read(data,platform):
 r=Reader(data,platform);entity=r.entity()
 if r.pos!=len(data):raise ValueError(f'unconsumed entity bytes {len(data)-r.pos}')
 return entity,r.events

def u32(v):return struct.pack('<I',v)
def array(data,size):
 if len(data)%size:raise ValueError('unaligned array')
 return u32(len(data)//size)+data
class Writer:
 def __init__(self,platform,software=False):self.platform=platform;self.software=software
 def volume(self,v):
  if not v['class']:return u32(0)
  return u32(v['class'])+u32(v['name'])+v.get('bounds',v.get('cylinder',b''))
 def block(self,b):
  flags=b['flags']&~8 if self.software else b['flags']
  out=u32(b['class'])+struct.pack('<HHH',b['first'],b['count'],flags)
  if b['class'] in [iw_hash('CIwModelBlockGLUVs'),iw_hash('CIwModelBlockGLUVs2')]:return out+b['data']
  colors=b['colors'];mode=b['mode']
  if len(colors)!=b['count']*4:raise ValueError('color count mismatch')
  if self.platform=='ngage' and mode&4:mode&=~4
  out+=bytes([mode])
  if mode&1:
   if any(colors[i]!=colors[i+1] or colors[i]!=colors[i+2] or colors[i+3]!=255 for i in range(0,len(colors),4)):raise ValueError('invalid grayscale colors')
   return out+colors[::4]
  if mode&4:
   for i in range(0,len(colors),4):
    a,b0,c,alpha=colors[i:i+4];out+=struct.pack('<H',(a>>3)|((b0>>2)<<5)|((c>>3)<<11))
    if mode&2:out+=bytes([alpha])
   return out
  return out+bytes(colors[i*4+ch] for ch in range(4) for i in range(b['count']))
 def component(self,c):
  if 'reference' in c:return u32(c['reference'])
  kind=c['class'];out=u32(kind)
  if kind==iw_hash('CIwEntSpec'):return out+u32(c['name'])+self.entity(c['entity'])
  if kind==iw_hash('CIwRenderableModelSpec'):
   base=c['base']
   if self.software:base=b'\0'+base[1:2]+b'\0'*4+base[6:]
   flags=c['flags']&~16 if self.platform=='ngage' else c['flags']
   out+=self.volume(c['volume'])+base+bytes([flags])+u32(c['model'])+array(c['materials'],4)
   if flags&2:out+=self.block(c['colors'])
   if flags&16:out+=self.block(c['lightmap_uvs'])
   return out
  if kind==iw_hash('CIwColliderSpec'):return out+self.volume(c['volume'])+c['data']
  if kind in [iw_hash(s) for s in ['CTriggerVolumeSpec','CTriggerInteractableSpec','CDoorSpec','CWindowSpec','CTriggerSecurityKeypadSpec']]:
   out+=bytes([c['flags']])+array(c['references'],4)+u32(c['string_id'])+u32(c['extra'])
   if kind!=iw_hash('CTriggerVolumeSpec'):out+=c['interact']
   if kind==iw_hash('CDoorSpec'):out+=c['door']
   if kind==iw_hash('CWindowSpec'):out+=c['window']
   if kind==iw_hash('CTriggerSecurityKeypadSpec'):
    if len(c['keypad_label'])!=5 or c['keypad_label'][-1]!=0 or not c['keypad_label'][:4].isdigit():raise Unsupported('unobserved keypad label profile')
    out+=c['keypad_label']
   return out
  if kind==iw_hash('CRouteShortcutSpec'):
   if c['route_profile']!=1 or len(c['route_endpoints'])!=24 or c['route_flag']>1:raise Unsupported('unobserved route-shortcut profile')
   return out+u32(c['route_profile'])+c['route_endpoints']+bytes([c['route_flag']])
  if kind==iw_hash('CActionMessageSpec'):return out+u32(c['message_id'])
  if kind==iw_hash('CActionChangeLevelSpec'):return out+c['target']+c['data']
  return out+c.get('data',b'')
 def entity(self,e):
  out=bytes([e['flags']])+u32(len(e['components']))+b''.join(self.component(c) for c in e['components'])
  out+=e['position']+e['quaternion']
  if self.platform=='ios':out+=e['scale']
  elif e['scale']!=struct.pack('<3i',4096,4096,4096):raise Unsupported('non-unit scale needs baking')
  out+=e['ids']+bytes([e['active']])
  if self.platform=='ios':out+=array(e['extra'],4)
  elif e['extra']:raise Unsupported('additional entity data needs conversion')
  return out

def encode(entity,platform,software=False):return Writer(platform,software).entity(entity)
