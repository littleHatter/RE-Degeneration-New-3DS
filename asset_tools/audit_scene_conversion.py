"""Audit typed donor conversion and shared model references for damaged groups."""
from pathlib import Path
import argparse,json,collections
from group_codec import parse,iw_hash
from component_codec import read,encode,Unsupported
from directory_codec import parse as directory
from restore import decode

def audit(inputs,objects,out):
 inv=json.loads((objects/'inventory.json').read_text());catalog=json.loads((objects/'catalog.json').read_text());e=next(e for e in inv['ngage_main']['entries'] if e['path']=='common/environment.group.bin');env=decode((inputs/'ngage/game/main.dz').read_bytes(),e);models={r.name_hash for r in directory(env).records() if r.class_id==iw_hash('CIwModel') and r.offset};rows=[]
 def components(e):
  for c in e['components']:
   if 'entity' in c:yield from components(c['entity'])
   yield c
 for entry in inv['ngage_protected']['entries']:
  if entry.get('decompression')!='invalid' or not entry['name'].endswith('.group.bin'):continue
  candidates=[r for r in catalog if r['source']=='ios' and 'container' not in r and Path(r['path']).name==entry['name']]
  if len(candidates)!=1:raise ValueError('ambiguous donor group')
  d=candidates[0];g=parse((objects/d['object']).read_bytes());counts=collections.Counter();errors=collections.Counter();missing=collections.Counter();classes=collections.Counter()
  for r in g.resources():
   classes[f'{r.class_id:08x}']+=1
   if r.class_id!=iw_hash('CIwEntSpec'):continue
   try:
    e,_=read(r.body,'ios');assert encode(e,'ios')==r.body
    for c in components(e):
     if c.get('class')==iw_hash('CIwRenderableModelSpec') and c['model'] not in models:missing[f'{c["model"]:08x}']+=1
    b=encode(e,'ngage',True);assert encode(read(b,'ngage')[0],'ngage')==b;counts['convertible_entities']+=1
   except Unsupported as error:errors[str(error)]+=1
  rows.append({'path':d['path'],'entities':dict(counts),'unsupported':dict(errors),'missing_models':dict(missing),'classes':dict(classes)})
 out.write_text(json.dumps({'groups':rows},indent=2)+'\n');return rows
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();rows=audit(a.inputs,a.audit,a.report)
 for r in rows:print(r['path'],r['entities'],'unsupported',r['unsupported'],'missing',r['missing_models'])
