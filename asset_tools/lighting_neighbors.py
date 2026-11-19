"""Bounded, material/surface-filtered neighbor matching in model coordinates."""
import math,struct,itertools
from group_codec import iw_hash

def surfaces(model,points,software):
 materials=struct.unpack('<'+str(len(model['materials'])//4)+'I',model['materials']);out=[[] for p in points]
 def face(ids,material):
  for a,b,c in itertools.combinations(ids,3):
   u=[points[b][i]-points[a][i] for i in range(3)];v=[points[c][i]-points[a][i] for i in range(3)];n=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]);length=math.sqrt(sum(x*x for x in n))
   if length:
    normal=tuple(x/length for x in n)
    for j in ids:out[j].append((material,normal))
    break
 if software:
  group=next(b for b in model['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in group['roles']);slot=group['roles'][0];raw=struct.unpack('<'+str(len(group['indices'])//2)+'H',group['indices'])
  for b in model['blocks']:
   if b['class']!=iw_hash('CIwModelBlockBSP'):continue
   for p in b['primitives']:
    ids=struct.unpack('<'+str(len(p['indices'])//2)+'H',p['indices']);face([raw[j*stride+slot] for j in ids],materials[b['material']])
 else:
  for b in model['blocks']:
   if b['class']!=iw_hash('CIwModelBlockGLTriList'):continue
   ids=struct.unpack('<'+str(len(b['data'])//2)+'H',b['data'])
   for i in range(0,len(ids),3):face(ids[i:i+3],materials[b['material']])
 return out

def neighbor_weights(p,old_surfaces,donor_points,donor_surfaces,radius):
 eligible={}
 for j,q in enumerate(donor_points):
  distance=math.dist(p,q)
  if distance>radius:continue
  compatible=any(mat==other and abs(sum(a*b for a,b in zip(n,m)))>=.9 and abs(sum((p[i]-q[i])*n[i] for i in range(3)))<=max(2,radius*.1) for mat,n in old_surfaces for other,m in donor_surfaces[j])
  if compatible:eligible.setdefault(q,[]).append(j)
 nearest=sorted(eligible,key=lambda q:(math.dist(p,q),q))[:3]
 if not nearest:return {},{'method':'unresolved','radius':radius,'reason':'no nearby material/surface-compatible point'}
 total=sum(1/math.dist(p,q) for q in nearest);weights={j:(1/math.dist(p,q))/total/len(eligible[q]) for q in nearest for j in eligible[q]}
 return weights,{'method':'inverse_distance','radius':radius,'neighbors':[{'position':q,'distance':math.dist(p,q),'donor_indices':eligible[q]} for q in nearest]}
