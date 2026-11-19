"""Verify the observed keypad component against original/donor controls."""
from pathlib import Path
import json
from component_codec import read,encode
from group_codec import iw_hash

def check(root):
 rows=json.loads((root/'evidence/keypad_component/controls.json').read_text());results=[];payloads=[]
 for row in rows:
  body=bytes.fromhex(row['body']);platform='ios'
  entity,events=read(body,platform);assert encode(entity,platform)==body
  shutter=[e for e in events if e['class']==iw_hash('CTriggerSecurityKeypadSpec')]
  assert shutter and all(e['bytes']==42 for e in shutter)
  for event in shutter:
   start=event['offset'];payloads.append(body[start:start+42])
   for offset,value in [(start+37,65),(start+41,65)]:
    bad=bytearray(body);bad[offset]=value
    try:read(bytes(bad),platform)
    except ValueError:pass
    else:raise AssertionError('unobserved keypad profile accepted')
  converted=encode(entity,'ngage',True);assert encode(read(converted,'ngage')[0],'ngage')==converted
  for cut in [0,1,5,len(body)-1]:
   try:read(body[:cut],platform)
   except ValueError:pass
   else:raise AssertionError('truncated control accepted')
  results.append({'source':row['source'],'path':row['path'],'id':row['id'],'exact_roundtrip':True,'ngage_structural_roundtrip':True,'keypad_component_bytes':8,'truncated_controls_rejected':True,'unobserved_label_profiles_rejected':True})
 assert len(payloads)==2 and payloads[0]==payloads[1]
 assert {r['source'] for r in results}=={'ios','android'}
 (root/'reports/keypad_component_checks.json').write_text(json.dumps(results,indent=2)+'\n')
 print('Verified',len(results),'keypad controls')

if __name__=='__main__':check(Path(__file__).resolve().parents[1])
