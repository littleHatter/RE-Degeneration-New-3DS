"""Lossless Lua chunk framing and isolated existing-API diagnostic routes.
These are test scripts, never production/restoration replacements.
"""
import struct,copy
from audit_archives import validate_lua
U=lambda n:struct.pack('<I',n)
class Reader:
 def __init__(self,b):self.b=b;self.p=12
 def take(self,n):
  if n<0 or self.p+n>len(self.b):raise ValueError('Lua bounds')
  b=self.b[self.p:self.p+n];self.p+=n;return b
 def u32(self):return struct.unpack('<I',self.take(4))[0]
 def string(self):
  n=self.u32();return U(n)+self.take(n)
 def fn(self):
  source=self.string();header=self.take(12);code=self.take(self.u32()*4);constants=[]
  for _ in range(self.u32()):
   tag=self.take(1)[0]
   if tag==4:v=self.string()
   elif tag in [0,1,3]:v=self.take(4 if tag==3 else 1 if tag==1 else 0)
   else:raise ValueError('Lua tag')
   constants.append((tag,v))
  children=[self.fn() for _ in range(self.u32())];start=self.p;self.take(self.u32()*4)
  for _ in range(self.u32()):self.string();self.take(8)
  for _ in range(self.u32()):self.string()
  return dict(source=source,header=header,code=code,constants=constants,children=children,debug=self.b[start:self.p])
def encode(t):return t['source']+t['header']+U(len(t['code'])//4)+t['code']+U(len(t['constants']))+b''.join(bytes([tag])+v for tag,v in t['constants'])+U(len(t['children']))+b''.join(encode(p) for p in t['children'])+t['debug']
def load(b):
 validate_lua(b);r=Reader(b);t=r.fn();assert r.p==len(b) and b[:12]+encode(t)==b;return t

def skip_intro(data):
 tree=load(data);expected=copy.deepcopy(tree);assert expected['children'][3]['constants'][23]==(4,U(6)+b'Start\0')
 expected['children'][3]['constants'][23]=(4,U(8)+b'Explore\0');out=data[:12]+encode(expected);assert load(out)==expected;return out

def staff_route(data,scene="staffArea",spawn="leonspawn"):
 tree=load(data);result=copy.deepcopy(tree);fn=result['children'][16]
 assert fn['header'][8]==0 and fn['header'][9]==1 and fn['header'][11]>=4
 constants=[v[4:-1].decode() if tag==4 else None for tag,v in fn['constants']]
 idx={s:constants.index(s) for s in ['type','EventTypes','BEGIN_ROOM','Level','Load','leonspawn']};assert idx['type']<256
 if scene not in ['staffArea','planeCargo','warehouse','planeCrashed','generatorTunnels','infirmary','planeExit','dutyFreeWest','dutyFreeEast','vipPlane','security','planeEntrance']:raise ValueError('unsupported diagnostic scene')
 if spawn!='leonspawn':
  v=spawn.encode()+b'\0';fn['constants'][idx['leonspawn']]=(4,U(len(v))+v)
 name=scene.encode()+b'\0';staff=len(fn['constants']);fn['constants'].append((4,U(len(name))+name))
 abc=lambda op,a,b,c:op|(a<<6)|(c<<14)|(b<<23)
 abx=lambda op,a,bx:op|(a<<6)|(bx<<14)
 code=[abc(6,1,0,256+idx['type']),abx(5,2,idx['EventTypes']),abx(1,3,idx['BEGIN_ROOM']),abc(6,2,2,3),abc(23,0,1,2),abx(22,0,131077),abx(5,1,idx['Level']),abx(1,2,idx['Load']),abc(6,1,1,2),abx(1,2,staff),abx(1,3,idx['leonspawn']),abc(28,1,3,1),abc(30,0,1,0)]
 fn['code']=struct.pack('<13I',*code);fn['children']=[];fn['debug']=b'\0'*12
 out=data[:12]+encode(result);assert load(out)==result
 for i,p in enumerate(tree['children']):
  if i!=16:assert encode(p)==encode(result['children'][i])
 return out

def staff_route_once(data,spawn="leonspawn"):
 """Test-only first entry into Staff; retain the normal VIP handler thereafter."""
 tree=load(data);result=copy.deepcopy(tree);original=tree['children'][16]
 assert original['header'][8]==0 and original['header'][9]==1
 routed=load(staff_route(data,spawn=spawn))['children'][16]
 name=b'__RE_DIAG_STAFF_ENTERED\0';guard=len(routed['constants']);routed['constants'].append((4,U(len(name))+name))
 abc=lambda op,a,b,c:op|(a<<6)|(c<<14)|(b<<23)
 abx=lambda op,a,bx:op|(a<<6)|(bx<<14)
 old=list(struct.unpack('<13I',routed['code']));old[5]=abx(22,0,131080)
 code=[abx(5,1,guard),abc(2,2,1,0),abc(23,1,1,2),abx(22,0,131086)]+old[:6]+[abc(2,1,1,0),abx(7,1,guard)]+old[6:]+[abx(36,1,0),abc(0,2,0,0),abc(28,1,2,1),abc(30,0,1,0)]
 routed['code']=struct.pack('<23I',*code);routed['children']=[copy.deepcopy(original)];result['children'][16]=routed
 out=data[:12]+encode(result);assert load(out)==result and encode(load(out)['children'][16]['children'][0])==encode(original);return out
