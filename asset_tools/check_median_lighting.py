"""Ensure only the twelve recorded white defaults change."""
import argparse,json,collections
from group_codec import parse,iw_hash
from component_codec import read
from color_contract import ColorContract
from pathlib import Path

def renders(e,p=()):
 for i,c in enumerate(e['components']):
  if 'entity' in c:yield from renders(c['entity'],p+(i,))
  if c.get('class')==iw_hash('CIwRenderableModelSpec') and 'colors' in c:yield p+(i,),c

def check(previous,current,report):
 manifest=json.loads((current/'staff_bundle.json').read_text());expected={}
 for r in manifest['lightmap_bake']['instances']:
  if r.get('median_estimates'):expected[r['scene'],r['entity'],r['model']]={x['color_index']:bytes(x['rgba']) for x in r['median_estimates']}
 contract=ColorContract((current/'overrides/common/environment.group.bin').read_bytes());stats=collections.Counter()
 for path in ['levels/staffarea/staffarea.group.bin','levels/staffarea/staffarea_story.group.bin']:
  before={r.in_group_hash:r for r in parse((previous/'overrides'/path).read_bytes()).resources() if r.class_id==iw_hash('CIwEntSpec')}
  for r in parse((current/'overrides'/path).read_bytes()).resources():
   if r.class_id!=iw_hash('CIwEntSpec'):continue
   old=dict(renders(read(before[r.in_group_hash].body,'ngage')[0]))
   for key,c in renders(read(r.body,'ngage')[0]):
    a=old[key]['colors']['colors'];b=c['colors']['colors'];assert len(a)==len(b);assert c['colors']['count']>=contract.required[c['model']];stats['checked_arrays']+=1
    allowed=expected.get((path,f'{r.in_group_hash:08x}',f'{c["model"]:08x}'),{})
    for i in range(0,len(a),4):
     if i//4 in allowed:
      assert a[i:i+4]==b'\xff'*4 and b[i:i+4]==allowed[i//4] and b[i:i+4]!=b'\xff'*4;stats['white_defaults_replaced']+=1
     else:assert a[i:i+4]==b[i:i+4];stats['other_color_slots_unchanged']+=1
 assert stats['white_defaults_replaced']==12 and stats['checked_arrays']==448
 report.write_text(json.dumps(dict(stats),indent=2)+'\n');print(dict(stats))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--previous',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.previous,a.current,a.report)
