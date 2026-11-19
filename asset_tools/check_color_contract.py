"""Verify every Staff Area color index and reject speculative nonconstant repairs."""
from pathlib import Path
import argparse,json,collections,copy,tempfile
from staff_pipeline import build
from color_contract import ColorContract
from group_codec import parse,iw_hash
from component_codec import read,Unsupported

def check(inputs,audit,report):
 with tempfile.TemporaryDirectory() as tmp:
  a=Path(tmp)/'a';b=Path(tmp)/'b';first=build(inputs,audit,a);second=build(inputs,audit,b);assert first==second
  contract=ColorContract((a/'overrides/common/environment.group.bin').read_bytes());assert len(contract.required)==485
  count=0;fixed=[]
  def visit(e):
   nonlocal count
   for c in e['components']:
    if 'entity' in c:visit(c['entity'])
    if c.get('class')!=iw_hash('CIwRenderableModelSpec') or 'colors' not in c:continue
    assert c['colors']['count']>=contract.required[c['model']];count+=1
    if c['model']==0x935d80dd:fixed.append(c)
  for path in ['levels/staffarea/staffarea.group.bin','levels/staffarea/staffarea_story.group.bin']:
   for r in parse((a/'overrides'/path).read_bytes()).resources():
    if r.class_id==iw_hash('CIwEntSpec'):visit(read(r.body,'ngage')[0])
  assert count==448 and first['statistics']['constant_color_extensions']==1
  c=copy.deepcopy(fixed[0]);assert c['colors']['count']==37;c['colors']['count']=36;c['colors']['colors']=b'\xff'*144
  stats=collections.Counter();contract.ensure(c,stats);assert c['colors']['colors']==b'\xff'*148
  bad=copy.deepcopy(c);bad['colors']['count']=36;bad['colors']['colors']=b'\0'*4+b'\xff'*140
  try:contract.ensure(bad,collections.Counter())
  except Unsupported:pass
  else:raise AssertionError('nonconstant short array was guessed')
  result={'software_models_indexed':485,'safe_scene_color_arrays':448,'constant_arrays_extended':1,'added_color_entries':1,'nonconstant_short_arrays_rejected':True,'repeatable_bundle':True}
 report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.inputs,a.audit,a.report)
