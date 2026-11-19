"""Build a complete intact-scene control with donor entity conversion.
Original lighting is explicitly retained for this format control, not reconstructed.
Unsupported entities retain their intact original records, with coverage reported.
"""
import sys,json,copy,collections,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re_restore_work/tools'))
from group_codec import parse,encode as encode_group,iw_hash
from restore import decode,sha
from component_codec import read,encode,Unsupported

def retain_lighting(donor,reference,stats):
 if len(donor['components'])!=len(reference['components']):raise Unsupported('component count differs from control')
 for new,old in zip(donor['components'],reference['components']):
  if new.get('class')!=old.get('class'):raise Unsupported('component type differs from control')
  if 'entity' in new:retain_lighting(new['entity'],old['entity'],stats)
  if new.get('class')==iw_hash('CIwRenderableModelSpec'):
   # Reference-only control: preserve all existing software rendering attributes.
   new['base']=old['base'];new['flags']=old['flags']
   if 'colors' in old:new['colors']=copy.deepcopy(old['colors']);stats['reference_lighting_blocks']+=1

def build(inputs,audit,path,output):
 inv=json.loads((audit/'inventory.json').read_text());cat=json.loads((audit/'catalog.json').read_text());e=next(e for e in inv['ngage_main']['entries'] if e['path']==path)
 original=decode((inputs/'ngage/game/main.dz').read_bytes(),e);ng=parse(original);entry=next(e for e in cat if e['source']=='ios' and e['path']==path and 'container' not in e)
 donor_bytes=(audit/entry['object']).read_bytes();assert sha(donor_bytes)==entry['sha256'],'donor object changed'
 donor=parse(donor_bytes);lookup={(r.class_id,r.in_group_hash):r for r in donor.resources()};result=copy.deepcopy(ng);stats=collections.Counter();unsupported=collections.Counter()
 for r in result.resources():
  if r.class_id!=iw_hash('CIwEntSpec'):continue
  d=lookup.get((r.class_id,r.in_group_hash))
  if not d:stats['original_without_matching_donor']+=1;continue
  try:
   before,_=read(r.body,'ngage');after,_=read(d.body,'ios');assert encode(before,'ngage')==r.body;assert encode(after,'ios')==d.body
   retain_lighting(after,before,stats);converted=encode(after,'ngage',True);parsed,_=read(converted,'ngage');assert encode(parsed,'ngage')==converted
  except Unsupported as error:unsupported[str(error).split(' at ')[0]]+=1;continue
  stats['converted_entities']+=1;stats['component_bearing_converted']+=bool(after['components']);stats['byte_identical']+=converted==r.body;r.body=converted
 payload=encode_group(result);assert encode_group(parse(payload))==payload
 output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(payload)
 report={'path':path,'scope':'typed donor entities inside complete intact scene; original lighting and unsupported records retained for this control',
  'original_sha256':sha(original),'donor_sha256':entry['sha256'],'output_sha256':sha(payload),'statistics':dict(stats),'retained_unsupported':dict(unsupported),'damaged_scene_restored':False}
 output.with_suffix(output.suffix+'.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--path',default='levels/vip/vip.group.bin');p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.inputs,a.audit,a.path,a.output)
