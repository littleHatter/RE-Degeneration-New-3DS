"""Check damaged-entry coverage and the narrowly scoped original-story repair."""
from pathlib import Path
import argparse,json,copy
from group_codec import parse,encode,iw_hash
from component_codec import read,encode as entity_encode
from restore import decode,sha

def check(inputs,audit,game,report):
 inv=json.loads((audit/'inventory.json').read_text());manifest=json.loads((game/'staff_bundle.json').read_text());rows=[]
 for source in ['ngage_main','ngage_protected']:
  for e in inv[source]['entries']:
   if e.get('decompression')!='invalid':continue
   matches=[r for r in manifest['files'] if Path(r['path']).name==e['name']]
   assert len(matches)==1,(e['name'],matches)
   r=matches[0];body=(game/'overrides'/r['path']).read_bytes();assert sha(body)==r['sha256']
   rows.append({'source':source,'original_name':e['name'],'replacement':r['path'],'original_directory_normalized':e['path']!=r['path'],'category':r['category']})
 assert len(rows)==24
 path='levels/security/security_story.group.bin';source,e=next((source,e) for source in ['ngage_main','ngage_protected'] for e in inv[source]['entries'] if e['name']==Path(path).name);arc='ngage/game/main.dz' if source=='ngage_main' else 'ngage/game/bin/protected.dz.ngdat';original=decode((inputs/arc).read_bytes(),e);g=parse(original);resources={f'{r.in_group_hash:08x}':r for r in g.resources() if r.class_id==iw_hash('CIwEntSpec')};repairs=manifest['native_story_color_repairs'];assert len(repairs)==2
 for edit in repairs:
  r=resources[edit['entity']];entity,_=read(r.body,'ngage');target=entity
  for i in edit['component'][:-1]:target=target['components'][i]['entity']
  c=target['components'][edit['component'][-1]];assert f'{c["model"]:08x}'==edit['model'];old=c['colors']['colors'];new=bytes(edit['new_colors']);assert len(old)==16 and c['colors']['count']==4 and len(new)==24 and new[:16]==old
  for m in edit['nearest_original_anchors']:
   assert m['new_slot'] in [4,5]
   assert all(new[m['new_slot']*4:m['new_slot']*4+4]==old[j*4:j*4+4] for j in m['original_slots'])
  if c['model']==0x2327b3fe:assert new[16:20]==old[:4] and new[20:24]==old[12:16]
  else:assert c['model']==0x935d894b and len(set(old[i:i+4] for i in range(0,16,4)))==1
  c['colors']['count']=6;c['colors']['colors']=new;r.body=entity_encode(entity,'ngage')
 assert encode(g)==(game/'overrides'/path).read_bytes()
 result={'damaged_original_entries_covered':len(rows),'damaged_groups_covered':sum(r['replacement'].endswith('.group.bin') for r in rows),'damaged_scripts_covered':sum(r['replacement'].endswith('.luc') for r in rows),'entries':rows,'native_security_story_changes_limited_to_two_color_array_extensions':True,'all_existing_story_color_entries_and_other_fields_preserved':True,'full_gameplay_verified':False};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='entries'},indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['inputs','audit','game','report']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();check(a.inputs,a.audit,a.game,a.report)
