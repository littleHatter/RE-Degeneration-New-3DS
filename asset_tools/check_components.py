"""Batch verification of typed entities, exact round trips and Staff conversion coverage."""
from pathlib import Path
import argparse,collections,json
from group_codec import parse,iw_hash,UnsupportedGroup
from restore import decode,sha
from component_codec import read,encode,Unsupported

def check(inputs,audit,out):
 inv=json.loads((audit/'inventory.json').read_text());catalog=json.loads((audit/'catalog.json').read_text());stats=collections.Counter();unsupported=collections.Counter();total=0
 for source,path in [('ngage_main','ngage/game/main.dz'),('ngage_protected','ngage/game/bin/protected.dz.ngdat')]:
  raw=(inputs/path).read_bytes()
  for e in inv[source]['entries']:
   if e.get('kind')!='resource group':continue
   try:ng=parse(decode(raw,e))
   except UnsupportedGroup:continue
   ds=[d for d in catalog if d['source']=='ios' and d['path']==e['path'] and d['kind']=='resource group']
   if len(ds)!=1:continue
   donor_bytes=(audit/ds[0]['object']).read_bytes();assert sha(donor_bytes)==ds[0]['sha256'],'donor object changed'
   donor=parse(donor_bytes);lookup={(r.class_id,r.in_group_hash):r for r in donor.resources()}
   for r in ng.resources():
    if r.class_id!=iw_hash('CIwEntSpec') or (r.class_id,r.in_group_hash) not in lookup:continue
    total+=1
    for platform,b in [('ngage',r.body),('ios',lookup[r.class_id,r.in_group_hash].body)]:
     try:entity,events=read(b,platform)
     except Unsupported as error:unsupported[(platform,str(error).split(' at ')[0])]+=1;continue
     assert encode(entity,platform)==b,'typed roundtrip mismatch'
     stats[platform]+=1
 scene=[]
 for path in ['levels/staffarea/staffarea.group.bin','levels/staffarea/staffarea_story.group.bin']:
  d=next(d for d in catalog if d['source']=='ios' and d['path']==path and 'container' not in d);data=(audit/d['object']).read_bytes();assert sha(data)==d['sha256'],'donor object changed';g=parse(data);rows=[]
  for r in g.resources():
   if r.class_id!=iw_hash('CIwEntSpec'):continue
   entity,events=read(r.body,'ios');assert encode(entity,'ios')==r.body
   old=encode(entity,'ngage',True);parsed,_=read(old,'ngage');assert encode(parsed,'ngage')==old;assert encode(entity,'ngage',True)==old
   for cut in [0,1,5,len(r.body)-1]:
    try:read(r.body[:cut],'ios')
    except ValueError:pass
    else:raise AssertionError('truncated entity accepted')
   rows.append({'id':r.in_group_hash,'source_sha256':sha(r.body),'converted_sha256':sha(old),'component_records_including_nested':len(events)})
  scene.append({'path':path,'entity_records':len(rows),'typed_roundtrip':'byte-identical','ngage_structural_roundtrip':'passed',
   'truncation_tests':'passed','repeatable_conversion':True,'runtime_accepted':False,'records':rows})
 report={'matched_entity_pairs':total,'typed_roundtrips':dict(stats),'unsupported_corpus_branches':[{'platform':p,'reason':reason,'records':n} for (p,reason),n in sorted(unsupported.items())],
  'staff_area':scene,'scope':'entity formats only; no claim of model/lighting/collision conversion or complete scene restoration'}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'pairs':total,'roundtrips':dict(stats),'staff_entities':sum(len(s['records']) for s in scene)},indent=2));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.inputs,a.audit,a.report)
