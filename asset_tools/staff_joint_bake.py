"""Staff-only, RGB area fit with equality constraints on complete coplanar shared edges.
Requires numpy, scipy, texture2ddecoder, Unicorn (verified transform conversion).
"""
import struct,math,json,collections,argparse
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from group_codec import parse,encode,iw_hash
from component_codec import read
from model_codec import read as glread
from software_model_codec import read as swread
from lightmap_bake import LightmapBake,points
from shared_edge_lighting import SeamPass,cross,dot,sub
from restore import decode

def continuous_light(a,b,threshold=24):
 return a is not None and b is not None and a[1]==b[1] and max(abs(x-y) for x,y in zip(a[0],b[0]))<=threshold

def component(entity,trail):
 for i in trail[:-1]:entity=entity['components'][i]['entity']
 return entity['components'][trail[-1]]
def faces(model):
 for block in model['blocks']:
  if block['class']!=iw_hash('CIwModelBlockGLTriList'):continue
  ids=struct.unpack('<'+'H'*block['count'],block['data']);at=0
  while at<len(ids):
   t=ids[at:at+3];quad=at+6<=len(ids) and ids[at+3:at+5]==(t[0],t[2]) and len(set(ids[at:at+6]))==4
   yield (t[0],t[1],t[2],ids[at+5]) if quad else t
   at+=6 if quad else 3

def quadrature(p,uv,ids,steps):
 xyz=[p[j] for j in ids]
 if len(ids)==4:
  for i in range(steps):
   x=(i+.5)/steps
   for j in range(steps):
    y=(j+.5)/steps;b=((1-x)*(1-y),x*(1-y),x*y,(1-x)*y)
    dx=[sum(xyz[k][a]*v for k,v in enumerate((-(1-y),1-y,y,-y))) for a in range(3)]
    dy=[sum(xyz[k][a]*v for k,v in enumerate((-(1-x),-x,x,1-x))) for a in range(3)]
    jac=math.sqrt(dot(cross(dx,dy),cross(dx,dy)))
    yield b,tuple(sum(uv[ids[k]][a]*b[k] for k in range(4)) for a in range(2)),jac/(steps*steps)
 else:
  cr=cross(sub(xyz[1],xyz[0]),sub(xyz[2],xyz[0]));area=math.sqrt(dot(cr,cr))/(2*steps*steps)
  for i in range(steps):
   for j in range(steps-i):
    x,y=(i+1/3)/steps,(j+1/3)/steps;b=(1-x-y,x,y)
    yield b,tuple(sum(uv[ids[k]][a]*b[k] for k in range(3)) for a in range(2)),area
    if i+j<steps-1:
     x,y=(i+2/3)/steps,(j+2/3)/steps;b=(1-x-y,x,y)
     yield b,tuple(sum(uv[ids[k]][a]*b[k] for k in range(3)) for a in range(2)),area

def solve(h,rhs,initial):
 # Solve RGB independently with the same geometry matrix; no conversion to luminance.
 scale=max(float(np.max(np.diag(h))),1);h=h/scale;rhs=rhs/scale;result=[];checks=[]
 for ch in range(3):
  def fg(x):return float(x@h@x-2*x@rhs[:,ch]),2*(h@x-rhs[:,ch])
  r=minimize(fg,initial[:,ch],jac=True,bounds=[(0,255)]*len(h),method='L-BFGS-B',options={'ftol':1e-14,'gtol':1e-7,'maxiter':3000,'maxls':40})
  if not r.success:raise ValueError('bounded RGB fit failed: '+str(r.message))
  result.append(r.x);checks.append({'channel':ch,'iterations':r.nit,'status':str(r.message)})
 return np.array(result).T,checks

def rebake(checkpoint,game,out,report):
 inv=json.loads((checkpoint/'reports/inventory.json').read_text());path='levels/staffarea/staffarea.group.bin'
 def donor(name):return decode((checkpoint/'inputs/ios/main.dz').read_bytes(),next(e for e in inv['ios']['entries'] if e['path']==name))
 source=parse(donor(path));src={f'{r.in_group_hash:08x}':read(r.body,'ios')[0] for r in source.resources() if r.class_id==iw_hash('CIwEntSpec')}
 env=(game/'overrides/common/environment.group.bin').read_bytes();baker=LightmapBake(env,donor('common/environment.group.bin'));tex=[r.body for r in source.resources() if r.class_id==iw_hash('CIwTexture')];assert len(tex)==1;baker.atlas(tex[0],'clamp')
 g=parse((game/'overrides'/path).read_bytes());eligible=set();selected={}
 def visit(e,root,trail=()):
  for k,c in enumerate(e['components']):
   if 'entity' in c:visit(c['entity'],root,trail+(k,))
   if c.get('class')!=iw_hash('CIwRenderableModelSpec') or 'lightmap_uvs' not in c:continue
   try:m=glread(baker.donor[c['model']])
   except KeyError:continue
   p=points(m,False);ext=sorted(max(v[k] for v in p)-min(v[k] for v in p) for k in range(3));base=c.get('colors',{}).get('colors',b'\xff'*(len(p)*4))
   if ext[0]>32 or ext[1]*ext[2]<1000000 or len({base[i:i+4] for i in range(0,len(base),4)})!=1:continue
   eligible.add((path,root,f'{c["model"]:08x}'));selected[root,trail+(k,)]=c
 for root,e in src.items():visit(e,root)
 seam=SeamPass(env,game/'resident_evil.xe3u');edge_cache={};edge_stats=collections.Counter()
 def endpoint(node,instances):
  if node in edge_cache:return edge_cache[node]
  ii,ci=node;instance=instances[ii];dc=selected.get((instance['entity'],tuple(instance['trail'])))
  if dc is None:return None
  h=dc['model'];n,mapping,_,_=baker.correspondence(h);ids=mapping.get(ci,{})
  if not ids:return None
  uv=list(zip(*[iter(struct.unpack('<'+'h'*(n*2),dc['lightmap_uvs']['data']))]*2));base=dc.get('colors',{}).get('colors',b'\xff'*(n*4))[:3]
  color=tuple(sum(baker.sample(*uv[j])[ch]*weight for j,weight in ids.items())/sum(ids.values())*base[ch]/255 for ch in range(3))
  edge_cache[node]=color,base;return edge_cache[node]
 def edge_filter(nodes,instances):
  for a,b in nodes:
   ca,cb=endpoint(a,instances),endpoint(b,instances)
   if ca is None or cb is None:return False
   if not continuous_light(ca,cb):
    edge_stats['source_light_discontinuities_retained']+=1;return False
  return True
 topology=seam.apply([(path,g)],eligible,collect_only=True,edge_filter=edge_filter);topology.update(edge_stats)
 # Native slots are the actual output variables. Weld only topology-approved shared edges.
 parent={}
 def find(n):
  parent.setdefault(n,n)
  if parent[n]!=n:parent[n]=find(parent[n])
  return parent[n]
 def join(a,b):
  a,b=find(a),find(b)
  if a!=b:parent[max(a,b)]=min(a,b)
 for cluster in seam.clusters:
  for node in cluster[1:]:join(cluster[0],node)
 entries=[];stats=collections.Counter()
 for ii,instance in enumerate(seam.instances):
  key=instance['entity'],tuple(instance['trail'])
  if key not in selected:continue
  c=instance['component'];dc=selected[key];dm=glread(baker.donor[c['model']]);dp=points(dm,False);nm=swread(baker.native[c['model']]);np_=points(nm,True)
  uv=list(zip(*[iter(struct.unpack('<'+'h'*(len(dp)*2),dc['lightmap_uvs']['data']))]*2));base=dc.get('colors',{}).get('colors',b'\xff'*(len(dp)*4))
  ig=next(b for b in nm['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in ig['roles']);ind=struct.unpack('<'+'H'*(len(ig['indices'])//2),ig['indices']);slots=collections.defaultdict(set)
  for i in range(0,len(ind),stride):slots[np_[ind[i+ig['roles'][0]]]].add(ind[i+ig['roles'][2]])
  mapping=[];ambiguous=False
  for p in dp:
   roots={find((ii,ci)) for ci in slots[p]}
   if len(roots)!=1:ambiguous=True;break
   mapping.append(next(iter(roots)))
  if ambiguous:
   stats['complex_mapping_instances_retained']+=1;continue
  for ids in faces(dm):
   span=max(max(uv[j][a] for j in ids)-min(uv[j][a] for j in ids) for a in range(2));steps=max(16,min(48,math.ceil(span*max(baker.width,baker.height)/4096/2)))
   for basis,texcoord,area in quadrature(dp,uv,ids,steps):
    color=baker.sample(*texcoord);target=tuple(color[a]*base[a]/255 for a in range(3));coeff=collections.defaultdict(float)
    for v,w in zip(ids,basis):coeff[mapping[v]]+=w
    if area>0:
     old_rgb=sum(np.array([sum(c['colors']['colors'][ci*4+ch] for ci in slots[dp[v]])/len(slots[dp[v]]) for ch in range(3)])*weight for v,weight in zip(ids,basis))
     entries.append((dict(coeff),np.array(target),area,old_rgb))
   stats['faces']+=1
  stats['instances']+=1
 nodes=sorted({node for weights,_,_,_ in entries for node in weights});index={node:i for i,node in enumerate(nodes)};n=len(nodes);h=np.zeros((n,n));rhs=np.zeros((n,3));initial=np.zeros((n,3))
 for node,i in index.items():ii,ci=node;initial[i]=list(seam.instances[ii]['component']['colors']['colors'][ci*4:ci*4+3])
 for weights,target,area,old_rgb in entries:
  for a,wa in weights.items():
   ai=index[a];rhs[ai]+=area*wa*target
   for b,wb in weights.items():h[ai,index[b]]+=area*wa*wb
 values,checks=solve(h,rhs,initial);before_loss=after_loss=0.;total=0.
 for weights,target,area,old_rgb in entries:
  a=old_rgb;b=sum(values[index[node]]*weight for node,weight in weights.items());before_loss+=float(np.sum((a-target)**2))*area;after_loss+=float(np.sum((b-target)**2))*area;total+=area
 before_edges=[];worst_edges=[]
 for pairs in seam.accepted_edges:
  for a,b in pairs:
   ca=seam.instances[a[0]]['component']['colors']['colors'][a[1]*4:a[1]*4+3];cb=seam.instances[b[0]]['component']['colors']['colors'][b[1]*4:b[1]*4+3];gap=max(abs(x-y) for x,y in zip(ca,cb));before_edges.append(gap);worst_edges.append({'gap':gap,'position':seam.node_positions[a][0],'entity_a':seam.instances[a[0]]['entity'],'entity_b':seam.instances[b[0]]['entity']})
 changes=0
 for ii,instance in enumerate(seam.instances):
  block=instance['component']['colors'];data=bytearray(block['colors'])
  for ci in range(block['count']):
   node=find((ii,ci))
   if node not in index:continue
   color=bytes(np.rint(values[index[node]]).astype('uint8'));start=ci*4
   changes+=data[start:start+3]!=color;data[start:start+3]=color
  block['colors']=bytes(data);block['mode']=0
 for pairs in seam.accepted_edges:
  for a,b in pairs:
   def rgba(node):return seam.instances[node[0]]['component']['colors']['colors'][node[1]*4:node[1]*4+4]
   assert rgba(a)==rgba(b)
 from component_codec import encode as entencode
 for r,e in seam.records:r.body=entencode(e,'ngage')
 out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(encode(g));assert encode(parse(out.read_bytes()))==out.read_bytes()
 result={'scope':path,'method':'joint area-weighted bounded RGB least squares; shared-edge equality built into fit','topology':topology,'statistics':dict(stats),'quadrature_samples':len(entries),'joint_variables':n,'maximum_shared_edge_RGB_gap_before':max(before_edges,default=0),'maximum_shared_edge_RGB_gap_after':0,'changed_color_slots':changes,'worst_old_shared_corners':sorted(worst_edges,key=lambda r:-r['gap'])[:8],'area_weighted_rgb_rmse_before':math.sqrt(before_loss/(3*total)),'area_weighted_rgb_rmse_after':math.sqrt(after_loss/(3*total)),'solver':checks,'RGB_channels_independent':True,'alpha_preserved':True};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__)
 for k in ['checkpoint','game','out','report']:a.add_argument('--'+k,type=Path,required=True)
 rebake(**vars(a.parse_args()))
