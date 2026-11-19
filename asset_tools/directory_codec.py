"""Verified directory-indexed group index, with opaque resource storage retained.
Only the layout observed in the three supplied environment groups is supported.
Offsets are absolute. Zero-offset index entries remain unresolved index references.
Resource bodies are NOT inferred to be semantically compatible across platforms.
"""
from dataclasses import dataclass
import struct
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re_restore_work/tools'))
from group_codec import Cursor,MEMBERS,DIRECTORY
@dataclass
class IndexRecord:
 class_id:int
 name_hash:int
 offset:int
@dataclass
class DirectoryGroup:
 header:bytes
 member_payload:bytes
 version:int
 classes:list
 storage:bytes
 storage_offset:int
 def records(self):return [r for cl,rows in self.classes for r in rows]
 def spans(self):
  rows=sorted((r for r in self.records() if r.offset),key=lambda r:r.offset)
  end=self.storage_offset+len(self.storage)
  return [(r,r.offset+8,rows[i+1].offset if i+1<len(rows) else end) for i,r in enumerate(rows)]
def parse(data):
 c=Cursor(data);header=c.take(6)
 if header[:2]!=b'\x3d\x03' or c.u32()!=MEMBERS:raise ValueError('unsupported indexed group header')
 n=c.u32()
 if n<4:raise ValueError('invalid member section length')
 members=c.take(n-4)
 if c.u32()!=DIRECTORY:raise ValueError('missing resource directory')
 n=c.u32()
 if n<9:raise ValueError('invalid resource directory length')
 p=Cursor(c.take(n-4));version=p.u8();count=p.u32()
 if version!=1 or not 0<count<=512:raise ValueError('unsupported directory version/count')
 classes=[]
 for _ in range(count):
  cl=p.u32();num=p.u32()
  if num>65536:raise ValueError('excessive index count')
  rows=[IndexRecord(cl,p.u32(),p.u32()) for _ in range(num)];classes.append((cl,rows))
 if p.pos!=len(p.data):raise ValueError('unconsumed directory bytes')
 storage_offset=c.pos;storage=data[c.pos:];group=DirectoryGroup(header,members,version,classes,storage,storage_offset)
 offsets=set()
 for r in group.records():
  if not r.offset:continue
  if r.offset<storage_offset or r.offset+8>len(data) or r.offset in offsets:raise ValueError('invalid resource offset')
  offsets.add(r.offset)
  if struct.unpack_from('<II',data,r.offset)!=(r.class_id,r.name_hash):raise ValueError('index/resource header mismatch')
 if not storage.endswith(b'\0'*8):raise ValueError('unexpected indexed storage tail')
 return group
def encode(g):
 out=bytearray(g.header)+struct.pack('<II',MEMBERS,len(g.member_payload)+4)+g.member_payload
 p=bytearray(struct.pack('<BI',g.version,len(g.classes)))
 for cl,rows in g.classes:
  p+=struct.pack('<II',cl,len(rows))
  for r in rows:p+=struct.pack('<II',r.name_hash,r.offset)
 out+=struct.pack('<II',DIRECTORY,len(p)+4)+p
 if len(out)!=g.storage_offset:raise ValueError('directory layout changed; offsets need explicit relocation')
 return bytes(out)+g.storage
