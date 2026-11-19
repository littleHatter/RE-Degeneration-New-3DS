"""Repair only two observed underfilled original Security story color arrays.
Existing colors stay intact. New entries copy the nearest original color anchor
using the native model's vertex/color index table; ambiguity is rejected.
"""
import struct,copy
from group_codec import parse,encode,iw_hash
from directory_codec import parse as directory
from software_model_codec import read as model_read
from component_codec import read as entity_read,encode as entity_encode
from lightmap_bake import points

TARGETS={0x2327b3fe,0x935d894b}
def repair(body,environment):
 models={}
 for r,s,t in directory(environment).spans():
  if r.class_id==iw_hash('CIwModel') and r.name_hash in TARGETS:models[r.name_hash]=model_read(environment[s:t])
 g=parse(body);edits=[]
 def visit(entity,root,trail):
  for i,c in enumerate(entity['components']):
   at=trail+[i]
   if 'entity' in c:visit(c['entity'],root,at)
   if c.get('model') not in TARGETS or 'colors' not in c:continue
   colors=c['colors'];m=models[c['model']];p=points(m,True);ig=next(b for b in m['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(x<128 for x in ig['roles']);ind=struct.unpack('<'+'H'*(len(ig['indices'])//2),ig['indices']);positions={}
   for k in range(0,len(ind),stride):
    vi,ci=ind[k+ig['roles'][0]],ind[k+ig['roles'][2]]
    if ci in positions and positions[ci]!=p[vi]:raise ValueError('ambiguous color position')
    positions[ci]=p[vi]
   need=max(positions)+1;have=colors['count']
   if have>=need:continue
   if (have,need)!=(4,6):raise ValueError('unobserved original story bounds profile')
   old=colors['colors'];new=bytearray(old);mapping=[]
   for ci in range(have,need):
    distances={j:sum((positions[ci][k]-positions[j][k])**2 for k in range(3)) for j in range(have)}
    best=min(distances.values());nearest=[j for j,v in distances.items() if v==best];values={old[j*4:j*4+4] for j in nearest}
    if len(values)!=1:raise ValueError('ambiguous nearest original color')
    new+=next(iter(values));mapping.append({'new_slot':ci,'original_slots':nearest,'distance_squared':best})
   colors['count']=need;colors['colors']=bytes(new)
   assert colors['colors'][:have*4]==old
   edits.append({'entity':f'{root:08x}','component':at,'model':f'{c["model"]:08x}','original_count':have,'new_count':need,'original_colors':list(old),'new_colors':list(new),'nearest_original_anchors':mapping})
 for r in g.resources():
  if r.class_id!=iw_hash('CIwEntSpec'):continue
  e,_=entity_read(r.body,'ngage');visit(e,r.in_group_hash,[]);r.body=entity_encode(e,'ngage')
 if len(edits)!=2:raise ValueError('unexpected Security story repair count')
 return encode(g),edits
