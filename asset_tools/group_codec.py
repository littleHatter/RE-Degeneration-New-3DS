"""Strict, lossless group framing reader; resource bodies remain explicit opaque bytes.
Format reference: Tatsh/dade Marmalade reader (MIT); see reference/dade/revision.json.
This module rejects uncertain record boundaries instead of guessing them.
"""
from dataclasses import dataclass,field
import struct

def iw_hash(text):
 value=5381
 for c in text.lower().encode('ascii'):value=(value*33+c)&0xffffffff
 return value
CLASSES=['CIwTexture','CIwMaterial','CIwModel','CIwGxFont','CIwResGroup','CIwResList','CIwResTemplate','CIwAnim','CIwAnimSkin','CIwAnimSkel','CIwAnimKeyFrame','CIwAnimTrack','CIwSound','CIwSoundSpec','CIwSoundGroup','CIwResBinary']
CLASS_NAMES={iw_hash(s):s for s in CLASSES}
MEMBERS=iw_hash('ResGroupMembers');RESOURCES=iw_hash('ResGroupResources');DIRECTORY=iw_hash('ResGroupDirectory')
class UnsupportedGroup(ValueError):pass
class Cursor:
 def __init__(self,data,offset=0):self.data=data;self.pos=offset
 def take(self,n):
  if n<0 or self.pos+n>len(self.data):raise ValueError('truncated group field')
  value=self.data[self.pos:self.pos+n];self.pos+=n;return value
 def u32(self):return struct.unpack('<I',self.take(4))[0]
 def u8(self):return self.take(1)[0]
@dataclass
class Resource:
 class_id:int
 name_hash:int|None
 in_group_hash:int
 body:bytes
 offset:int
 size:int
@dataclass
class ResourceClass:
 class_id:int
 names_omitted:int
 has_size:int
 resources:list=field(default_factory=list)
@dataclass
class Section:
 kind:int
 payload:bytes
 classes:list|None=None
@dataclass
class Group:
 header:bytes
 sections:list
 trailing:bytes
 name:str|None=None
 def resources(self):return [r for s in self.sections if s.classes for cls in s.classes for r in cls.resources]

def parse(data):
 c=Cursor(data)
 header=c.take(6)
 if header[:2]!=b'\x3d\x03':raise ValueError('unsupported group signature')
 sections=[];name=None
 while True:
  kind=c.u32()
  if not kind:break
  if kind==DIRECTORY:raise UnsupportedGroup("directory-indexed group variant; no verified typed reader")
  size=c.u32()
  if size<4:raise ValueError('invalid section size')
  absolute=c.pos;payload=c.take(size-4);section=Section(kind,payload)
  if kind==MEMBERS:
   end=payload.find(b'\0')
   if end<0:raise ValueError('missing group name terminator')
   name=payload[:end].decode('ascii')
  if kind==RESOURCES:
   p=Cursor(payload);count=p.u32()
   if count>512:raise ValueError('too many resource classes')
   section.classes=[]
   for _ in range(count):
    class_id=p.u32();number=p.u32();omit=p.u8();has_size=p.u8()
    if omit not in [0,1] or has_size!=1 or number>65536:raise ValueError('unsupported resource framing')
    cls=ResourceClass(class_id,omit,has_size);section.classes.append(cls)
    for _ in range(number):
     start=p.pos;resource_size=p.u32();name_hash=None if omit else p.u32();in_group_hash=p.u32();end=start+resource_size
     if end<p.pos or end>len(payload):raise ValueError('resource exceeds section')
     body=p.take(end-p.pos);cls.resources.append(Resource(class_id,name_hash,in_group_hash,body,absolute+start,resource_size))
   if p.pos!=len(payload):raise ValueError('unconsumed resource section bytes')
  sections.append(section)
 trailing=data[c.pos:]
 if trailing and any(trailing):raise ValueError('unconsumed group tail')
 return Group(header,sections,trailing,name)

def encode(group):
 out=bytearray(group.header)
 for section in group.sections:
  payload=section.payload
  if section.classes is not None:
   p=bytearray(struct.pack('<I',len(section.classes)))
   for cls in section.classes:
    p+=struct.pack('<IIBB',cls.class_id,len(cls.resources),cls.names_omitted,cls.has_size)
    for resource in cls.resources:
     record=bytearray()
     if not cls.names_omitted:record+=struct.pack('<I',resource.name_hash)
     record+=struct.pack('<I',resource.in_group_hash)+resource.body
     p+=struct.pack('<I',len(record)+4)+record
   payload=bytes(p)
  out+=struct.pack('<II',section.kind,len(payload)+4)+payload
 out+=b'\0'*4+group.trailing
 return bytes(out)
