"""Area-weighted projection for coarse structural meshes, not point-only sampling."""
import math,struct,collections
from group_codec import iw_hash
from lightmap_bake import points

def project(model,uv,sample,steps=8):
 p=points(model,False);ext=sorted(max(v[k] for v in p)-min(v[k] for v in p) for k in range(3))
 if ext[0]>32 or ext[1]*ext[2]<1000000:return None
 sums=collections.defaultdict(lambda:[0.,0.,0.]);weights=collections.defaultdict(float);matrix=collections.defaultdict(lambda:collections.defaultdict(float))
 def add(vs,bary,area):
  u,v=[sum(uv[vs[j]][k]*bary[j] for j in range(len(vs))) for k in range(2)];light=sample(u,v)
  for j,vi in enumerate(vs):
   w=area*bary[j];weights[vi]+=w
   for k,vk in enumerate(vs):matrix[vi][vk]+=w*bary[k]
   for ch in range(3):sums[vi][ch]+=light[ch]*w
 def area_of(a,b):return math.sqrt(sum(v*v for v in [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]))
 for block in model['blocks']:
  if block['class']!=iw_hash('CIwModelBlockGLTriList'):continue
  ids=struct.unpack('<'+'H'*block['count'],block['data']);start=0
  while start<len(ids):
   tri=ids[start:start+3];quad=start+6<=len(ids) and ids[start+3:start+5]==(tri[0],tri[2]) and len(set(ids[start:start+6]))==4
   vs=(tri[0],tri[1],tri[2],ids[start+5]) if quad else tri;start+=6 if quad else 3
   if any(uv[v]==(-4096,8192) for v in vs):continue
   if quad:
    xyz=[p[v] for v in vs]
    for i in range(steps):
     x=(i+.5)/steps
     for j in range(steps):
      y=(j+.5)/steps;bary=((1-x)*(1-y),x*(1-y),x*y,(1-x)*y)
      dx=[sum(xyz[k][axis]*v for k,v in enumerate((-(1-y),1-y,y,-y))) for axis in range(3)];dy=[sum(xyz[k][axis]*v for k,v in enumerate((-(1-x),-x,x,1-x))) for axis in range(3)]
      add(vs,bary,area_of(dx,dy))
   else:
    a,b,c=[p[v] for v in vs];ab=[b[k]-a[k] for k in range(3)];ac=[c[k]-a[k] for k in range(3)];area=area_of(ab,ac)
    if area==0:continue
    for i in range(steps):
     for j in range(steps-i):
      x,y=(i+1/3)/steps,(j+1/3)/steps;add(vs,(1-x-y,x,y),area)
      if i+j<steps-1:
       x,y=(i+2/3)/steps,(j+2/3)/steps;add(vs,(1-x-y,x,y),area)
 if not weights:return None
 ids=sorted(weights);n=len(ids);a=[[matrix[vi][vj] for vj in ids]+sums[vi] for vi in ids]
 for col in range(n):
  pivot=max(range(col,n),key=lambda row:abs(a[row][col]));a[col],a[pivot]=a[pivot],a[col]
  if abs(a[col][col])<1e-8:raise ValueError('singular surface projection')
  divisor=a[col][col];a[col]=[x/divisor for x in a[col]]
  for row in range(n):
   if row==col:continue
   factor=a[row][col]
   if factor:a[row]=[a[row][k]-factor*a[col][k] for k in range(n+3)]
 return {vi:tuple(max(0.,min(255.,a[row][n+ch])) for ch in range(3)) for row,vi in enumerate(ids)}
