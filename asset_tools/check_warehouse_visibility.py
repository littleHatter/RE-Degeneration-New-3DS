"""Check a local low-light correction against the previous Warehouse batch."""
from pathlib import Path
import argparse,json,copy
from group_codec import parse,iw_hash
from component_codec import read
from color_contract import ColorContract

def check(before,after,report):
 manifest=json.loads((after/'staff_bundle.json').read_text());profile=manifest['warehouse_visibility'];assert profile['minimum_rgb']==[[54,57,54],[74,77,74]];changed=arrays=0;minimum=999;maximum=-999;mode_promotions=0
 for e in profile['edits']:
  assert e['before'][3]==e['after'][3] and all(e['after'][i]>=e['before'][i] for i in range(3))
  assert all(e['after'][ch]==max(e['before'][ch],e['minimum_rgb'][ch]) for ch in range(3))
 constraints={(r['entity'],tuple(r['component']),r['color_index']):r['minimum_rgb'] for r in profile['minimum_constraints']}
 final_colors={}
 def gather(e,root,trail=()):
  for k,c in enumerate(e['components']):
   if 'entity'in c:gather(c['entity'],root,trail+(k,))
   if 'colors'in c:
    data=c['colors']['colors']
    for ci in range(len(data)//4):final_colors[root,trail+(k,),ci]=tuple(data[ci*4:ci*4+3])
 path='levels/warehouse/warehouse.group.bin';contract=ColorContract((after/'overrides/common/environment.group.bin').read_bytes());a=parse((before/'overrides'/path).read_bytes());b=parse((after/'overrides'/path).read_bytes())
 def compare(x,y):
  nonlocal arrays,changed,minimum,maximum,mode_promotions
  x=copy.deepcopy(x);y=copy.deepcopy(y)
  def strip(e,f):
   nonlocal arrays,changed,minimum,maximum,mode_promotions
   for c,d in zip(e['components'],f['components']):
    if 'entity'in c:strip(c['entity'],d['entity'])
    if 'colors'not in c:continue
    arrays+=1;p,q=c['colors'],d['colors'];assert p['count']==q['count'] and q['count']>=contract.required[d['model']]
    assert len(p['colors'])==len(q['colors'])
    for i in range(0,len(p['colors']),4):
     old,new=p['colors'][i:i+4],q['colors'][i:i+4];assert old[3]==new[3]
     if old!=new:changed+=1
     for ch in range(3):minimum=min(minimum,new[ch]-old[ch]);maximum=max(maximum,new[ch]-old[ch])
    p['colors']=q['colors']=b''
    if p['mode']!=q['mode']:assert p['mode']&1 and q['mode']==0;mode_promotions+=1;p['mode']=q['mode']
  strip(x,y);assert x==y,'non-color entity field changed'
 ar,br=list(a.resources()),list(b.resources());assert len(ar)==len(br)
 for x,y in zip(ar,br):
  assert (x.class_id,x.in_group_hash,x.name_hash)==(y.class_id,y.in_group_hash,y.name_hash)
  if x.class_id==iw_hash('CIwEntSpec'):
   after_entity=read(y.body,'ngage')[0];compare(read(x.body,'ngage')[0],after_entity);gather(after_entity,f'{y.in_group_hash:08x}')
  else:assert x.body==y.body
 for p in (before/'overrides').rglob('*'):
  if p.is_file() and p.relative_to(before/'overrides').as_posix()!=path:assert p.read_bytes()==(after/'overrides'/p.relative_to(before/'overrides')).read_bytes()
 assert minimum>=0 and maximum<=77
 for key,floor in constraints.items():assert all(final_colors[key][ch]>=floor[ch] for ch in range(3))
 result={'warehouse_arrays_checked':arrays,'final_changed_color_slots_including_seam_reconciliation':changed,'minimum_RGB_channel_change':minimum,'maximum_RGB_channel_change':maximum,'geometry_materials_transforms_and_other_entity_fields_unchanged':True,'alpha_unchanged':True,'all_other_override_files_byte_identical':True,'encoding_promotions':mode_promotions,'all_final_minimum_RGB_constraints_satisfied':len(constraints)};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.before,a.after,a.report)
