"""Reconcile colors only at complete coplanar shared edges of baked instances."""
import struct,math,collections,itertools
from group_codec import iw_hash
from component_codec import read,encode
from software_model_codec import read as mesh_read
from lightmap_bake import models,points
from engine_rotation import EngineRotation,rotate,compose,IDENTITY

def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def dot(a,b):return sum(x*y for x,y in zip(a,b))
class SeamPass:
 def __init__(self,environment,executable):self.meshes=models(environment,mesh_read);self.rotation=EngineRotation(executable)
 def apply(self,groups,eligible,minimum_constraints=None,collect_only=False,edge_filter=None):
  minimum_constraints=minimum_constraints or {}
  # Each element is (path, parsed group). Entity changes are serialized only at end.
  instances=[];records=[];stats=collections.Counter()
  def visit(e,pm,pp,path,root,trail):
   if struct.unpack('<3i',e['scale'])!=(4096,4096,4096):raise ValueError('seam pass requires unit scale')
   m,p=compose(self.rotation.matrix(e['quaternion']),struct.unpack('<3i',e['position']),pm,pp)
   for k,c in enumerate(e['components']):
    if 'entity' in c:visit(c['entity'],m,p,path,root,trail+(k,))
    if c.get('class')!=iw_hash('CIwRenderableModelSpec') or 'colors' not in c:continue
    if (path,root,f'{c["model"]:08x}') not in eligible:continue
    instances.append({'component':c,'matrix':m,'translation':p,'entity':root,'trail':trail+(k,),'model':f'{c["model"]:08x}'})
  for path,g in groups:
   for r in g.resources():
    if r.class_id==iw_hash('CIwEntSpec'):
     e,_=read(r.body,'ngage');records.append((r,e));visit(e,IDENTITY,(0.,0.,0.),path,f'{r.in_group_hash:08x}',())
  vertices=[];faces=[];slot_positions=collections.defaultdict(set)
  for ii,instance in enumerate(instances):
   c=instance['component'];mesh=mesh_read(self.meshes[c['model']]);local=points(mesh,True);world=[tuple(a+b for a,b in zip(rotate(v,instance['matrix']),instance['translation'])) for v in local]
   ind=next(b for b in mesh['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in ind['roles']);vs,cs=ind['roles'][0],ind['roles'][2]
   if cs>=128:continue
   indices=struct.unpack('<'+str(len(ind['indices'])//2)+'H',ind['indices']);materials=c['materials'] or mesh['materials'];materials=struct.unpack('<'+str(len(materials)//4)+'I',materials)
   for block in mesh['blocks']:
    if block['class']!=iw_hash('CIwModelBlockBSP'):continue
    for primitive in block['primitives']:
     raw=struct.unpack('<'+str(len(primitive['indices'])//2)+'H',primitive['indices']);order=[0,1,3,2] if len(raw)==4 else [0,1,2];corners=[]
     for j in order:
      vi,ci=indices[raw[j]*stride+vs],indices[raw[j]*stride+cs];vid=len(vertices);vertices.append(world[vi]);corners.append((vid,(ii,ci)));slot_positions[ii,ci].add(vid)
     positions=[vertices[v] for v,node in corners];normal=None
     for a,b,d in itertools.combinations(positions,3):
      n=cross(sub(b,a),sub(d,a));length=math.sqrt(dot(n,n))
      if length>1e-8:normal=tuple(x/length for x in n);break
     if normal is not None:faces.append({'corners':corners,'normal':normal,'center':tuple(sum(v[i] for v in positions)/len(positions) for i in range(3)),'material':materials[block['material']]})
  # Deterministic spatial welding, tolerance two native model units.
  bins=collections.defaultdict(list);canonical=[];ids=[];tol=2.
  for v in vertices:
   key=tuple(math.floor(x/tol) for x in v);candidates=[]
   for delta in itertools.product([-1,0,1],repeat=3):
    for ci in bins[tuple(key[i]+delta[i] for i in range(3))]:
     if math.dist(v,canonical[ci])<=tol:candidates.append(ci)
   if candidates:ci=min(candidates)
   else:ci=len(canonical);canonical.append(v);bins[key].append(ci)
   ids.append(ci)
  ambiguous={node for node,vs in slot_positions.items() if len({ids[v] for v in vs})>1};stats['ambiguous_color_slots_excluded']=len(ambiguous)
  edges=collections.defaultdict(list)
  for fi,face in enumerate(faces):
   corners=face['corners']
   for i,(a,an) in enumerate(corners):
    b,bn=corners[(i+1)%len(corners)];ca,cb=ids[a],ids[b]
    if ca==cb or an in ambiguous or bn in ambiguous:continue
    key=tuple(sorted((ca,cb)));edges[key].append((fi,{ca:an,cb:bn}))
  parents={}
  def find(n):
   parents.setdefault(n,n)
   if parents[n]!=n:parents[n]=find(parents[n])
   return parents[n]
  def join(a,b):
   a,b=find(a),find(b)
   if a!=b:parents[max(a,b)]=min(a,b)
  accepted=[]
  for edge,entries in sorted(edges.items()):
   for (ia,na),(ib,nb) in itertools.combinations(entries,2):
    if ia==ib:continue
    a,b=faces[ia],faces[ib]
    if abs(dot(a['normal'],b['normal']))<.999:continue
    if edge_filter is None and a['material']!=b['material']:continue
    direction=sub(canonical[edge[1]],canonical[edge[0]]);sa=cross(direction,sub(a['center'],canonical[edge[0]]));sb=cross(direction,sub(b['center'],canonical[edge[0]]))
    if dot(sa,sb)>=-1e-6:continue # overlapping/same-side faces are not adjoining
    nodes=[(na[v],nb[v]) for v in edge]
    def rgba(node):
     c=instances[node[0]]['component']['colors']['colors'];return c[node[1]*4:node[1]*4+4]
    if any(rgba(x)[3]!=rgba(y)[3] for x,y in nodes):continue
    if edge_filter is not None and not edge_filter(nodes,instances):continue
    if a['material']!=b['material']:stats['cross_material_edges']+=1
    for x,y in nodes:join(x,y)
    accepted.append(nodes)
  clusters=collections.defaultdict(list)
  for node in parents:clusters[find(node)].append(node)
  self.node_positions={node:[vertices[v] for v in sorted(vs)] for node,vs in slot_positions.items()};self.records=records;self.instances=instances;self.clusters=list(clusters.values());self.accepted_edges=accepted
  if collect_only:return {'instances':len(instances),'matched_edge_pairs':len(accepted),'endpoint_clusters':sum(len(v)>1 for v in self.clusters),'cross_instance_edges':sum(any(a[0]!=b[0] for a,b in pairs) for pairs in accepted),'cross_material_edges':stats['cross_material_edges']}
  edits=[]
  for cluster in clusters.values():
   cluster=sorted(set(cluster))
   if len(cluster)<2:continue
   colors=[instances[ii]['component']['colors']['colors'][ci*4:ci*4+4] for ii,ci in cluster];value=bytes(round(sum(c[ch] for c in colors)/len(colors)) for ch in range(4))
   floors=[minimum_constraints.get((instances[ii]['entity'],tuple(instances[ii]['trail']),ci)) for ii,ci in cluster]
   floors=[f for f in floors if f is not None]
   if floors:value=bytes([max(value[ch],max(f[ch] for f in floors)) for ch in range(3)]+[value[3]])
   for (ii,ci),before in zip(cluster,colors):
    if before==value:continue
    block=instances[ii]['component']['colors'];data=bytearray(block['colors']);data[ci*4:ci*4+4]=value;block['colors']=bytes(data)
    if block['mode']&1 and (value[3]!=255 or any(value[0]!=value[ch] for ch in [1,2])):
     block['mode']=0;stats['grayscale_blocks_promoted_to_RGBA']+=1
    edits.append({'entity':instances[ii]['entity'],'component':instances[ii]['trail'],'model':instances[ii]['model'],'color_index':ci,'before':list(before),'after':list(value)})
  for pairs in accepted:
   for a,b in pairs:
    ca=instances[a[0]]['component']['colors']['colors'][a[1]*4:a[1]*4+4];cb=instances[b[0]]['component']['colors']['colors'][b[1]*4:b[1]*4+4];assert ca==cb
  for r,e in records:r.body=encode(e,'ngage');assert encode(read(r.body,'ngage')[0],'ngage')==r.body
  return {'instances':len(instances),'matched_edge_pairs':len(accepted),'cross_instance_edge_pairs':sum(any(a[0]!=b[0] for a,b in pairs) for pairs in accepted),'endpoint_clusters':sum(len(v)>1 for v in clusters.values()),'changed_color_slots':len(edits),'exact_endpoint_equality_checks':len(accepted)*2,'statistics':dict(stats),'policy':'two-unit world tolerance; complete edges; same material; coplanar normals; opposite face interiors; exclude multi-position color slots; preserve alpha','edits':edits}
