"""Reference-guided low-light approximation for Warehouse equipment and fencing.
Only raise very dark colors on the selected prop materials; preserve alpha and
brighter samples. This is not recovery of the original lighting values.
"""
from pathlib import Path
import json,struct,collections
from group_codec import parse,encode,iw_hash
from component_codec import read,encode as entity_encode
from directory_codec import parse as directory
from software_model_codec import read as mesh_read
from lightmap_bake import points
from engine_rotation import EngineRotation,IDENTITY,rotate,compose
from restore import sha
TARGET_TEXTURES={0x66fc529f,0x960f8e02,0x1ebb6ad0,0x086c93e1}

def apply(game,report,low=(54,57,54),high=(74,77,74)):
 if len(low)!=3 or len(high)!=3 or any(not 0<=a<=b<=255 for a,b in zip(low,high)):raise ValueError('invalid minimum RGB profile')
 path='levels/warehouse/warehouse.group.bin';p=game/'overrides'/path;group=parse(p.read_bytes());env=(game/'overrides/common/environment.group.bin').read_bytes();rs={(r.class_id,r.name_hash):env[s:t-8 if t==len(env) else t] for r,s,t in directory(env).spans()};rotation=EngineRotation(game/'resident_evil.xe3u');records=[];selected=[]
 def visit(e,pm,pp,root,trail=()):
  if struct.unpack('<3i',e['scale'])!=(4096,4096,4096):raise ValueError('non-unit scale')
  m,t=compose(rotation.matrix(e['quaternion']),struct.unpack('<3i',e['position']),pm,pp)
  for k,c in enumerate(e['components']):
   if 'entity'in c:visit(c['entity'],m,t,root,trail+(k,))
   if c.get('class')!=iw_hash('CIwRenderableModelSpec') or 'colors'not in c:continue
   mesh=mesh_read(rs[iw_hash('CIwModel'),c['model']]);raw=c['materials'] or mesh['materials'];materials=struct.unpack('<'+str(len(raw)//4)+'I',raw);textures={struct.unpack_from('<I',rs[iw_hash('CIwMaterial'),h],5)[0] for h in materials if len(rs[iw_hash('CIwMaterial'),h])>=9}
   if not textures&TARGET_TEXTURES:continue
   world=[tuple(a+b for a,b in zip(rotate(v,m),t)) for v in points(mesh,True)];ind=next(b for b in mesh['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in ind['roles']);vs,cs=ind['roles'][0],ind['roles'][2]
   if cs>=128:continue
   values=struct.unpack('<'+str(len(ind['indices'])//2)+'H',ind['indices']);heights=collections.defaultdict(set)
   for i in range(0,len(values),stride):heights[values[i+cs]].add(world[values[i+vs]][1])
   selected.append((c,heights,root,trail+(k,),textures&TARGET_TEXTURES))
 for r in group.resources():
  if r.class_id==iw_hash('CIwEntSpec'):
   e,_=read(r.body,'ngage');records.append((r,e));visit(e,IDENTITY,(0.,0.,0.),f'{r.in_group_hash:08x}')
 all_y=[y for c,heights,*_ in selected for ys in heights.values() for y in ys]
 if not all_y:raise ValueError('no target props')
 bottom,top=min(all_y),max(all_y);edits=[];constraints=[]
 for c,heights,root,trail,textures in selected:
  b=c['colors'];data=bytearray(b['colors'])
  for ci,ys in heights.items():
   y=sum(ys)/len(ys);f=0 if top==bottom else (y-bottom)/(top-bottom);floor=tuple(round(low[ch]+(high[ch]-low[ch])*f) for ch in range(3));old=tuple(data[ci*4:ci*4+4])
   constraints.append({'entity':root,'component':trail,'color_index':ci,'minimum_rgb':floor})
   new=tuple(max(old[ch],floor[ch]) for ch in range(3))+(old[3],)
   if old==new:continue
   data[ci*4:ci*4+4]=bytes(new);edits.append({'entity':root,'component':trail,'model':f'{c["model"]:08x}','textures':[f'{h:08x}' for h in sorted(textures)],'color_index':ci,'world_y':y,'before':old,'after':new,'minimum_rgb':floor})
  b['colors']=bytes(data)
 for r,e in records:r.body=entity_encode(e,'ngage')
 payload=encode(group);assert encode(parse(payload))==payload;p.write_bytes(payload)
 result={'profile':'warehouse_equipment_faint_height_gradient','approximation':True,'target_texture_ids':[f'{h:08x}' for h in sorted(TARGET_TEXTURES)],'target_instances':len(selected),'height_range':[bottom,top],'minimum_rgb':[low,high],'changed_color_slots':len(edits),'alpha_unchanged':True,'minimum_constraints':constraints,'edits':edits}
 manifest=json.loads((game/'staff_bundle.json').read_text());row=next(r for r in manifest['files'] if r['path']==path);row.update(sha256=sha(payload),bytes=len(payload));manifest['warehouse_visibility']=result;(game/'staff_bundle.json').write_text(json.dumps(manifest,indent=2)+'\n');report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['edits','minimum_constraints']},indent=2));return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();apply(a.game,a.report)
