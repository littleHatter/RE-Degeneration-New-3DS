"""Approximate donor lightmaps as per-instance software vertex colors.
Exact correspondence is preferred, followed by bounded surface-aware neighbors
and recorded median estimates. Atlas border clamping and shared indices are explicit.
"""
import struct,math,collections,statistics
from group_codec import iw_hash
from directory_codec import parse as directory
from software_model_codec import read as swread
from model_codec import read as glread
from component_codec import Unsupported

def points(m,software):
 b=next(b for b in m['blocks'] if b['class']==iw_hash('CIwModelBlockVerts'));n=b['unique'];raw=b['values'][2:] if software else b['data'];a=struct.unpack('<'+str(n*3)+'h',raw[:n*6]);p=list(zip(a[:n],a[n:2*n],a[2*n:]))
 tail=raw[n*6:]
 if tail:p.extend(p[i] for i in struct.unpack('<'+str(len(tail)//2)+'H',tail))
 if len(p)!=b['count']:raise ValueError('vertex count')
 return p

def models(data,reader):
 out={}
 for r,s,t in directory(data).spans():
  if r.class_id!=iw_hash('CIwModel'):continue
  out[r.name_hash]=data[s:t-8 if t==len(data) else t]
 return out

class LightmapBake:
 def __init__(self,native,donor):
  self.native=models(native,swread);self.donor=models(donor,glread);self.cache={};self.stats=collections.Counter();self.rows=[]
 def atlas(self,body,address_mode="clamp"):
  if address_mode not in ["clamp","repeat"]:raise ValueError("unknown address mode")
  self.address_mode=address_mode
  import texture2ddecoder
  blob=body[23:-1]
  if body[0]!=0x14 or body[10]!=35 or len(blob)<72:raise Unsupported('lightmap texture wrapper')
  token,levels,w,h,size=struct.unpack_from('<5I',blob,8)
  if token!=0x8c02 or size!=max(w,8)*max(h,8)//2 or w*h>1048576:raise Unsupported('PVRTC4 lightmap profile')
  if len(blob)<72+size:raise ValueError('short lightmap')
  self.width,self.height=w,h;self.pixels=texture2ddecoder.decode_pvrtc(blob[72:72+size],w,h,False)
  if len(self.pixels)!=w*h*4:raise ValueError('decoded lightmap length')
  self.stats['atlases_decoded']+=1
 def sample(self,u,v):
  if not(0<=u<=4096 and 0<=v<=4096):
   if self.address_mode=='repeat':u%=4096;v%=4096;self.stats['wrapped_uv_samples']+=1
   else:self.stats['clamped_uv_samples']+=1
  x=min(4096,max(0,u))*self.width/4096-.5;y=min(4096,max(0,v))*self.height/4096-.5;ix=math.floor(x);iy=math.floor(y);fx=x-ix;fy=y-iy
  values=[0.,0.,0.]
  for dx,wx in [(0,1-fx),(1,fx)]:
   for dy,wy in [(0,1-fy),(1,fy)]:
    k=(min(self.height-1,max(0,iy+dy))*self.width+min(self.width-1,max(0,ix+dx)))*4
    for ch in range(3):values[ch]+=self.pixels[k+2-ch]*wx*wy
  return tuple(values)
 def correspondence(self,h):
  if h in self.cache:return self.cache[h]
  old=swread(self.native[h]);new=glread(self.donor[h]);op=points(old,True);np=points(new,False)
  from lighting_neighbors import surfaces,neighbor_weights
  os=surfaces(old,op,True);ns=surfaces(new,np,False)
  diagonal=math.dist(tuple(min(p[i] for p in op) for i in range(3)),tuple(max(p[i] for p in op) for i in range(3)));radius=min(128.,diagonal*.1)
  group=next(b for b in old['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in group['roles']);vs,cs=group['roles'][0],group['roles'][2]
  if cs>=128:raise Unsupported('software model has no color slot')
  ind=struct.unpack('<'+str(len(group['indices'])//2)+'H',group['indices']);mapping=collections.defaultdict(dict);diagnostics=[];pervertex={};unresolved=set()
  for i in range(0,len(ind),stride):
   vi,ci=ind[i+vs],ind[i+cs]
   if vi not in pervertex:
    ids=[j for j,p in enumerate(np) if p==op[vi]]
    if ids:weights={j:1. for j in ids};info={'method':'exact'}
    else:weights,info=neighbor_weights(op[vi],os[vi],np,ns,radius)
    pervertex[vi]=(weights,info)
    if not ids:diagnostics.append({'old_vertex':vi,'position':op[vi],**info})
   weights,info=pervertex[vi]
   if not weights:unresolved.add(ci)
   for j,w in weights.items():mapping[ci][j]=max(mapping[ci].get(j,0),w)
   mapping[ci] # retain unresolved color slots
  result=(len(np),dict(mapping),diagnostics,unresolved);self.cache[h]=result;return result
 def bake(self,c):
  if 'lightmap_uvs' not in c:return
  h=c['model']
  try:n,mapping,diagnostics,unresolved=self.correspondence(h)
  except (Unsupported,KeyError) as error:
   self.stats['unbaked_instances']+=1;self.rows.append({'model':f'{h:08x}','unbaked_reason':str(error)});return False
  block=c['lightmap_uvs']
  if block['count']!=n:raise Unsupported('lightmap UV/model count')
  uv=list(zip(*[iter(struct.unpack('<'+str(n*2)+'h',block['data']))]*2));old=c.get('colors');base=old['colors'] if old else b'\xff'*(n*4)
  if len(base)!=n*4:raise Unsupported('lightmap source color count')
  placeholder=(-4096,8192) if self.address_mode=='repeat' else None
  placeholder_count=sum(pair==placeholder for pair in uv)
  raw_samples=[None if pair==placeholder else self.sample(*pair) for pair in uv]
  fallback=None
  if placeholder_count:
   valid=[v for v in raw_samples if v is not None]
   if not valid:raise Unsupported('fully placeholder lightmap requires another lighting profile')
   fallback=tuple(statistics.median(v[ch] for v in valid) for ch in range(3))
   self.stats['placeholder_uv_samples_using_instance_median']+=placeholder_count
  projection=None
  if getattr(self,'coarse_surface_projection',False) and len({base[i:i+4] for i in range(0,len(base),4)})==1:
   from lightmap_footprint import project
   projection=project(glread(self.donor[h]),uv,self.sample)
   if projection:
    raw_samples=[projection.get(j,value) for j,value in enumerate(raw_samples)]
    self.stats['coarse_surface_projected_instances']+=1
  sampled=[]
  for j,value in enumerate(raw_samples):
   if value is None:value=fallback
   sampled.append(tuple(value[ch]*base[j*4+ch]/255 for ch in range(3))+(base[j*4+3],))
  need=max(mapping)+1
  constants={base[i:i+4] for i in range(0,len(base),4)}
  if unresolved and len(constants)!=1:self.stats['nonconstant_sources_using_median_fallback']+=1
  # Every unresolved slot receives a sampled median below; no source index guess.
  default=next(iter(constants)) if len(constants)==1 else b'\xff'*4
  colors=bytearray(default*need);seams=0
  for ci,ids in mapping.items():
   if ci in unresolved:continue
   if not ids:raise ValueError('empty geometric mapping')
   seams+=len({uv[j] for j in ids})>1
   for ch in range(4):colors[ci*4+ch]=max(0,min(255,round(sum(sampled[j][ch]*weight for j,weight in ids.items())/sum(ids.values()))))
  median_rows=[]
  if unresolved:
   from lighting_neighbors import surfaces
   om=swread(self.native[h]);nm=glread(self.donor[h]);op=points(om,True);np=points(nm,False);os=surfaces(om,op,True);ns=surfaces(nm,np,False)
   group=next(b for b in om['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in group['roles']);vs,cs=group['roles'][0],group['roles'][2];ind=struct.unpack('<'+str(len(group['indices'])//2)+'H',group['indices'])
   for ci in sorted(unresolved):
    vertices={ind[i+vs] for i in range(0,len(ind),stride) if ind[i+cs]==ci}
    candidates=[j for j,q in enumerate(np) if any(mat==other and abs(sum(a*b for a,b in zip(normal,m)))>=.9 and abs(sum((op[vi][axis]-q[axis])*normal[axis] for axis in range(3)))<=12.8 for vi in vertices for mat,normal in os[vi] for other,m in ns[j])]
    method='same_material_surface_median'
    if not candidates:candidates=list(range(n));method='instance_median'
    # Give each geometric position equal weight despite exported UV duplicates.
    by_position=collections.defaultdict(list)
    for j in candidates:by_position[np[j]].append(sampled[j])
    values=[tuple(statistics.median(v[ch] for v in samples) for ch in range(4)) for samples in by_position.values()]
    estimate=bytes(max(0,min(255,round(statistics.median(v[ch] for v in values)))) for ch in range(4))
    colors[ci*4:ci*4+4]=estimate
    median_rows.append({'color_index':ci,'method':method,'candidate_positions':len(values),'rgba':list(estimate)})
    self.stats[method]+=1
  c['flags']|=2;c['colors']={'class':iw_hash('CIwModelBlockCols'),'first':old['first'] if old else 44,'count':need,'flags':0,'mode':0,'colors':bytes(colors)}
  self.stats['baked_instances']+=1;self.stats['output_colors']+=need;self.stats['averaged_seam_or_merged_colors']+=seams
  self.stats['fallback_vertices']+=sum(d['method']=='inverse_distance' for d in diagnostics);self.stats['unresolved_vertices']+=sum(d['method']=='unresolved' for d in diagnostics);self.stats['median_color_slots']+=len(unresolved)
  self.rows.append({'model':f'{h:08x}','source_vertices':n,'output_colors':need,'averaged_seam_or_merged_colors':seams,'fallback_vertices':diagnostics,'retained_color_slots':[],'median_estimates':median_rows,'placeholder_uv_samples':placeholder_count,'placeholder_light_median':fallback,'area_weighted_projection':bool(projection)});return True

