"""Batch-convert verified entity transforms within an intact scene control.
Unconverted records come from the intact original, never a damaged donor.
This is a format-control experiment, not a reconstructed damaged scene.
"""
import sys,json,copy,collections,struct,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re_restore_work/tools'))
from group_codec import parse,encode,iw_hash
from restore import decode,sha
from entity_transform import convert,fields

def build(inputs,inventory,catalog,objects,out):
 path='levels/vip/vip.group.bin';e=next(e for e in inventory['ngage_main']['entries'] if e['path']==path)
 original=decode((inputs/'ngage/game/main.dz').read_bytes(),e);ng=parse(original)
 d=next(e for e in catalog if e['source']=='ios' and e['path']==path and 'container' not in e);ios=parse((objects/d['object']).read_bytes());donors={(r.class_id,r.in_group_hash):r for r in ios.resources()};result=copy.deepcopy(ng);changed=[]
 for r in result.resources():
  if r.class_id!=iw_hash('CIwEntSpec') or (r.class_id,r.in_group_hash) not in donors:continue
  b=donors[r.class_id,r.in_group_hash].body
  if b[:5]!=b'\0'*5:continue
  new=convert(b);before=fields(r.body);after=fields(new)
  assert all(before[k]==after[k] for k in ['quaternion','identifiers','flags'])
  assert max(abs(x-y) for x,y in zip(before['position'],after['position']))<=1
  changed.append({'id':r.in_group_hash,'byte_identical':r.body==new,'sha256':sha(new)});r.body=new
 payload=encode(result);assert encode(parse(payload))==payload
 out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(payload)
 report={'logical_path':path,'scope':'verified component-free entity conversion; all remaining records retained from intact original',
  'original_sha256':sha(original),'donor_sha256':d['sha256'],'output_sha256':sha(payload),
  'converted_entities':len(changed),'byte_identical_entities':sum(r['byte_identical'] for r in changed),'entities':changed}
 out.with_suffix(out.suffix+'.json').write_text(json.dumps(report,indent=2)+'\n');print('Converted entity control records:',len(changed));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.inputs,json.loads((a.audit/'inventory.json').read_text()),json.loads((a.audit/'catalog.json').read_text()),a.audit,a.output)
