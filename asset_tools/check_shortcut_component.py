"""Verify the observed route-shortcut component against original/donor controls."""
from pathlib import Path
import json
from component_codec import read,encode
from group_codec import iw_hash

def check(root):
 rows=json.loads((root/'evidence/shortcut_component/controls.json').read_text());results=[];vip_payloads=[]
 for row in rows:
  body=bytes.fromhex(row['body']);platform='ios' if row['source']=='ios' else 'ngage'
  entity,events=read(body,platform);assert encode(entity,platform)==body
  shortcuts=[e for e in events if e['class']==iw_hash('CRouteShortcutSpec')]
  assert shortcuts and all(e['bytes']==33 for e in shortcuts)
  for event in shortcuts:
   start=event['offset']
   if row['path']=='levels/vip/vip.group.bin':vip_payloads.append(body[start:start+33])
   for offset in [start+4,start+32]:
    bad=bytearray(body);bad[offset]=2
    try:read(bytes(bad),platform)
    except ValueError:pass
    else:raise AssertionError('unobserved shortcut profile accepted')
  converted=encode(entity,'ngage',True);assert encode(read(converted,'ngage')[0],'ngage')==converted
  for cut in [0,1,5,len(body)-1]:
   try:read(body[:cut],platform)
   except ValueError:pass
   else:raise AssertionError('truncated control accepted')
  results.append({'source':row['source'],'path':row['path'],'id':row['id'],'exact_roundtrip':True,'ngage_structural_roundtrip':True,'shortcut_component_bytes':33,'truncated_controls_rejected':True,'unobserved_profiles_rejected':True})
 assert len(vip_payloads)==2 and vip_payloads[0]==vip_payloads[1]
 assert any(r['source']=='ngage_main' for r in results)
 (root/'reports/shortcut_component_checks.json').write_text(json.dumps(results,indent=2)+'\n')
 print('Verified',len(results),'shortcut controls')

if __name__=='__main__':check(Path(__file__).resolve().parents[1])
