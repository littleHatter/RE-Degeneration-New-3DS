"""Verify that seam smoothing changes only recorded color bytes and is idempotent."""
from pathlib import Path
import argparse,json,copy
from group_codec import parse,encode,iw_hash
from component_codec import read
from color_contract import ColorContract
from shared_edge_lighting import SeamPass

def check(before,after,scene,report):
 paths=[f'levels/{scene}/{scene}{s}.group.bin' for s in ['', '_story']];arrays=changed=0;groups=[]
 def compare(a,b):
  nonlocal arrays,changed
  x,y=copy.deepcopy(a),copy.deepcopy(b)
  def strip(e,other):
   nonlocal arrays,changed
   for c,d in zip(e['components'],other['components']):
    if 'entity' in c:strip(c['entity'],d['entity'])
    if c.get('class')==iw_hash('CIwRenderableModelSpec') and 'colors' in c:
     ac,bc=c['colors']['colors'],d['colors']['colors'];assert len(ac)==len(bc);arrays+=1;changed+=sum(ac[i:i+4]!=bc[i:i+4] for i in range(0,len(ac),4));c['colors']['colors']=b'';d['colors']['colors']=b''
     assert d['colors']['count']>=contract.required[d['model']]
  strip(x,y);assert x==y,'non-color entity field changed'
 contract=ColorContract((after/'overrides/common/environment.group.bin').read_bytes())
 for path in paths:
  a=parse((before/'overrides'/path).read_bytes());b=parse((after/'overrides'/path).read_bytes());ar=list(a.resources());br=list(b.resources());assert len(ar)==len(br)
  for x,y in zip(ar,br):
   assert (x.class_id,x.in_group_hash,x.name_hash)==(y.class_id,y.in_group_hash,y.name_hash)
   if x.class_id==iw_hash('CIwEntSpec'):compare(read(x.body,'ngage')[0],read(y.body,'ngage')[0])
   else:assert x.body==y.body
  groups.append((path,b))
 manifest=json.loads((after/'staff_bundle.json').read_text());expected=manifest['shared_edge_lighting'][scene];assert changed==expected['changed_color_slots']
 for p in (before/'overrides').rglob('*'):
  if p.is_file() and p.relative_to(before/'overrides').as_posix() not in paths:assert p.read_bytes()==(after/'overrides'/p.relative_to(before/'overrides')).read_bytes()
 eligible={(r['scene'],r['entity'],r['model']) for r in manifest['lightmap_bake']['instances'] if 'output_colors' in r};snapshots=[encode(g) for _,g in groups];again=SeamPass((after/'overrides/common/environment.group.bin').read_bytes(),after/'resident_evil.xe3u').apply(groups,eligible);assert again['changed_color_slots']==0 and snapshots==[encode(g) for _,g in groups]
 result={'scene':scene,'arrays_checked':arrays,'changed_color_slots':changed,'non_color_entity_fields_unchanged':True,'other_resource_bodies_unchanged':True,'other_override_files_unchanged':True,'second_pass_byte_identical':True,'mesh_color_index_contracts':'passed','shared_endpoint_equality_checks':expected['exact_endpoint_equality_checks']};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--scene',required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.before,a.after,a.scene,a.report)
