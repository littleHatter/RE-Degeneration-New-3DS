"""Flatten identified physical door meshes in reconstructed areas; pair shared openings.
No scene geometry, door logic, intrinsic textures or non-door colours are changed.
"""
from pathlib import Path
import struct,math,collections,json,argparse
from group_codec import parse,encode,iw_hash
from component_codec import read,encode as entencode
from model_additions import records
from software_model_codec import read as meshread
from lightmap_bake import points
from engine_rotation import EngineRotation,IDENTITY,compose,rotate

def visible_average(samples,floor=64):
 rgb=[sum(c[k] for c in samples)/len(samples) for k in range(3)]
 lum=sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))
 if lum<floor:
  # Blend toward white only as much as necessary to meet a visible luminance floor.
  t=(floor-lum)/(255-lum);rgb=[x+(255-x)*t for x in rgb]
 return tuple(min(255,math.ceil(x-1e-10)) for x in rgb)

def apply(game,report,floor=64):
 env=records((game/'overrides/common/environment.group.bin').read_bytes());meshes={h:meshread(b) for (cl,h),b in env.items() if cl==iw_hash('CIwModel')};rotation=EngineRotation(game/'resident_evil.xe3u');groups=[];known=set();physical={iw_hash(x) for x in ['CDoorSpec','CActionChangeLevelSpec','CMapIconDoorSpec','CMapIconDoorShutterSpec']}
 def allmodels(e):
  result=[]
  for c in e['components']:
   if 'model'in c:result.append(c['model'])
   if 'entity'in c:result+=allmodels(c['entity'])
  return result
 for p in sorted((game/'overrides/levels').rglob('*.group.bin')):
  g=parse(p.read_bytes());entities=[]
  for r in g.resources():
   if r.class_id!=iw_hash('CIwEntSpec'):continue
   e,_=read(r.body,'ngage');entities.append((r,e))
   def classify(e):
    if any(c['class'] in physical for c in e['components']):known.update(allmodels(e))
    for c in e['components']:
     if 'entity'in c:classify(c['entity'])
   classify(e)
  groups.append((p,g,entities))
 nodes=[]
 def visit(e,pm,pp,area,root,trail,partner):
  if struct.unpack('<3i',e['scale'])!=(4096,4096,4096):raise ValueError('non-unit door transform')
  m,p=compose(rotation.matrix(e['quaternion']),struct.unpack('<3i',e['position']),pm,pp)
  for c in e['components']:
   if c['class']==iw_hash('CDoorSpec'):partner=struct.unpack_from('<I',c['door'],4)[0]
  for k,c in enumerate(e['components']):
   if 'entity'in c:visit(c['entity'],m,p,area,root,trail+(k,),partner)
   if c.get('model') not in known or 'colors' not in c:continue
   model=meshes[c['model']];local=points(model,True);world=[tuple(x+y for x,y in zip(rotate(v,m),p)) for v in local];ext=[max(q[k] for q in local)-min(q[k] for q in local) for k in range(3)];axis=min([0,2],key=lambda a:ext[a]);normal=rotate(tuple(1. if k==axis else 0. for k in range(3)),m);tangent=(normal[2],0.,-normal[0])
   def interval(direction):
    v=[sum(x*y for x,y in zip(q,direction)) for q in world];return min(v),max(v)
   block=c['colors'];samples=list(zip(*[iter(block['colors'])]*4));nodes.append({'c':c,'area':area,'root':root,'trail':trail+(k,),'partner':partner,'normal':normal,'tangent':tangent,'world':world,'height':(min(q[1] for q in world),max(q[1] for q in world)),'samples':samples})
 for p,g,entities in groups:
  for r,e in entities:visit(e,IDENTITY,(0.,0.,0.),p.parent.name,r.in_group_hash,(),0)
 parents=list(range(len(nodes)))
 def find(i):
  while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
  return i
 def join(i,j):
  a,b=find(i),find(j)
  if a!=b:parents[max(a,b)]=min(a,b)
 pair_reasons=collections.Counter()
 for i,a in enumerate(nodes):
  for j in range(i):
   b=nodes[j]
   if a['area']!=b['area']:continue
   reason=None
   if a['root']==b['root']:reason='same_entity'
   elif a['partner']==b['root'] or b['partner']==a['root']:reason='explicit_door_partner'
   elif abs(sum(x*y for x,y in zip(a['normal'],b['normal'])))>.999 and max(abs(x-y) for x,y in zip(a['height'],b['height']))<=80:
    def intervals(node,d):
     vs=[sum(x*y for x,y in zip(q,d)) for q in node['world']];return min(vs),max(vs)
    an,bn=intervals(a,a['normal']),intervals(b,a['normal']);at,bt=intervals(a,a['tangent']),intervals(b,a['tangent'])
    plane_gap=abs(sum(an)/2-sum(bn)/2);edge_gap=max(at[0],bt[0])-min(at[1],bt[1])
    if plane_gap<=100 and edge_gap<=80:reason='adjoining_same_plane_opening'
   if reason:join(i,j);pair_reasons[reason]+=1
 clusters=collections.defaultdict(list)
 for i in range(len(nodes)):clusters[find(i)].append(i)
 rows=[]
 for ids in clusters.values():
  samples=[s for i in ids for s in nodes[i]['samples']];value=visible_average(samples,floor)
  for i in ids:
   n=nodes[i];block=n['c']['colors'];before=block['colors'];block['colors']=bytes(v for old in n['samples'] for v in (*value,old[3]));block['mode']=0
   assert block['colors'][3::4]==before[3::4]
  rows.append({'area':nodes[ids[0]]['area'],'renderables':len(ids),'entities':[f'{nodes[i]["root"]:08x}' for i in ids],'models':[f'{nodes[i]["c"]["model"]:08x}' for i in ids],'RGB':value,'luminance':sum(a*b for a,b in zip(value,(.2126,.7152,.0722)))})
 changed=[]
 for p,g,entities in groups:
  old=p.read_bytes()
  for r,e in entities:r.body=entencode(e,'ngage')
  new=encode(g)
  if old!=new:p.write_bytes(new);changed.append(str(p.relative_to(game)))
 result={'minimum_luminance':floor,'known_door_models':[f'{h:08x}' for h in sorted(known)],'door_renderables':len(nodes),'physical_opening_clusters':len(clusters),'pairing':dict(pair_reasons),'changed_files':changed,'openings':rows};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='openings'},indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--game',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--floor',type=int,default=64);apply(**vars(p.parse_args()))
