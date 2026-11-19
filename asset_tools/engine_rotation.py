"""Offline rotation conversion using the pinned original game's math routine.
No game state, inputs, asset files or runtime output is modified.
"""
from pathlib import Path
import struct,hashlib
class EngineRotation:
 def __init__(self,path):
  from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM
  from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP,UC_ARM_REG_LR
  self.regs=(UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP,UC_ARM_REG_LR);b=Path(path).read_bytes()
  if hashlib.sha256(b).hexdigest()!=PROFILE_HASH:raise ValueError('unverified rotation executable profile')
  base=struct.unpack_from('<I',b,52)[0];off,size,mem=struct.unpack_from('<3I',b,20)
  self.uc=Uc(UC_ARCH_ARM,UC_MODE_ARM);self.uc.mem_map(base,(mem+4095)&~4095);self.uc.mem_write(base,b[off:off+size]);self.uc.mem_map(0x60000000,0x10000);self.uc.mem_map(0x70000000,0x10000);self.entry=base+0xd6054-off+1;self.cache={}
 def matrix(self,serialized):
  if serialized in self.cache:return self.cache[serialized]
  if len(serialized)==5:
   if serialized[:4]!=b'\0\0\0@' or serialized[4]>=24:raise ValueError('compact rotation profile')
   q=struct.pack('<4I',1<<30,serialized[4],0,0)
  elif len(serialized)==16:q=serialized
  else:raise ValueError('quaternion framing')
  u=self.uc;u.mem_write(0x60001000,q);u.mem_write(0x60002000,b'\0'*48)
  for r,v in zip(self.regs,[0x60002000,0x60001000,0x7000fff0,0x6000fff1]):u.reg_write(r,v)
  u.emu_start(self.entry,0x6000fff0,count=100000)
  values=struct.unpack('<12i',u.mem_read(0x60002000,48));m=tuple(tuple(values[i*3+j]/4096 for j in range(3)) for i in range(3));self.cache[serialized]=m;return m
PROFILE_HASH='7f32766261d30de61491ffce9de8b9469e6a57c10d255d7576c7aa51a8cacf76'

def rotate(p,m):return tuple(sum(p[k]*m[k][j] for k in range(3)) for j in range(3))
def compose(m,p,parent_m,parent_p):
 # Row vectors: local rotation followed by parent rotation.
 r=tuple(rotate(row,parent_m) for row in m);t=rotate(p,parent_m);return r,tuple(t[i]+parent_p[i] for i in range(3))
IDENTITY=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))
