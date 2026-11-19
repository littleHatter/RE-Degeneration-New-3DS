"""Verify the observed message component against original/donor controls."""
from pathlib import Path
import json
from component_codec import read,encode
from group_codec import iw_hash

def check(root):
 rows=json.loads((root/'evidence/message_component/controls.json').read_text());results=[]
 for row in rows:
  body=bytes.fromhex(row['body']);platform='ios' if row['source']=='ios' else 'ngage'
  entity,events=read(body,platform);assert encode(entity,platform)==body
  shutter=[e for e in events if e['class']==iw_hash('CActionMessageSpec')]
  assert shutter and all(e['bytes']==8 for e in shutter)
  converted=encode(entity,'ngage',True);assert encode(read(converted,'ngage')[0],'ngage')==converted
  for cut in [0,1,5,len(body)-1]:
   try:read(body[:cut],platform)
   except ValueError:pass
   else:raise AssertionError('truncated control accepted')
  results.append({'source':row['source'],'path':row['path'],'id':row['id'],'exact_roundtrip':True,'ngage_structural_roundtrip':True,'message_component_bytes':8,'truncated_controls_rejected':True})
 assert any(r['source']=='ngage_main' for r in results)
 (root/'reports/message_component_checks.json').write_text(json.dumps(results,indent=2)+'\n')
 print('Verified',len(results),'message controls')

if __name__=='__main__':check(Path(__file__).resolve().parents[1])
