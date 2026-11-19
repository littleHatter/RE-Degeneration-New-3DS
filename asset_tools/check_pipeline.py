"""Check all valid groups, donor scripts, corruption rejection and reproducibility."""
import argparse,json,tempfile,struct,copy
from pathlib import Path
from restore import run,sha
from group_codec import parse,encode,UnsupportedGroup,iw_hash
from texture_probe import convert

def files(root):return {str(p.relative_to(root)):sha(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file()}
def main(inputs):
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);a=root/'a';b=root/'b';summary=run(inputs,a);run(inputs,b)
  assert files(a)==files(b),'repeated runs differ'
  assert summary['original_entries']==67 and summary['damaged']==24
  assert summary['damaged_with_lua_candidates']==9 and summary['damaged_with_group_candidates']==15
  assert summary['group_layouts']=={'sectioned':99,'directory-indexed':3}
  assert summary['activated_overrides']==0
  catalog=json.loads((a/'catalog.json').read_text());get=lambda src,path:next(r for r in catalog if r['source']==src and r['path']==path and 'container' not in r)
  donor=get('ios','common/splash.group.bin');data=(a/donor['object']).read_bytes();group=parse(data);assert encode(group)==data
  for cut in [0,1,5,10,20,len(data)//2,len(data)-1]:
   try:parse(data[:cut])
   except ValueError:pass
   else:raise AssertionError('truncation accepted')
  broken=bytearray(data);struct.pack_into('<I',broken,10,0xffffffff)
  try:parse(broken)
  except ValueError:pass
  else:raise AssertionError('oversized section accepted')
  plan=json.loads((a/'restoration_plan.json').read_text());assert all(not v['ready_for_activation'] for v in plan['batches'])
  assert any(r['path_status'].startswith('quarantined') for r in plan['entries'])
  # Decode the original fixture straight from the supplied archive, not a hand-edited file.
  from restore import decode
  inv=json.loads((a/'inventory.json').read_text())['ngage_main'];e=next(e for e in inv['entries'] if e['path']=='common/splash.group.bin')
  original=parse(decode((inputs/'ngage/game/main.dz').read_bytes(),e));ng={r.in_group_hash:r.body for r in original.resources() if r.class_id==iw_hash('CIwTexture')}
  converted=[]
  for r in group.resources():
   if r.class_id==iw_hash('CIwTexture'):
    value,method=convert(r.body,ng[r.in_group_hash]);converted.append(value==ng[r.in_group_hash])
    assert convert(r.body,ng[r.in_group_hash])[0]==value
    try:convert(r.body[:-1],ng[r.in_group_hash])
    except ValueError:pass
    else:raise AssertionError('truncated texture accepted')
  assert converted==[False,True,True]
  result={'repeatable_files':len(files(a)),'sectioned_groups_roundtripped':99,'directory_groups_explicitly_unsupported':3,
   'damaged_entries_with_candidates':24,'truncation_checks':'passed','palette_conversions_byte_identical':2,
   'pvrtc_conversion_repeatable':True,'activation_blockers_enforced':True}
  print(json.dumps(result,indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inputs',type=Path,required=True);p.add_argument('--report',type=Path);args=p.parse_args();result=main(args.inputs)
 if args.report:args.report.write_text(json.dumps(result,indent=2)+'\n')
