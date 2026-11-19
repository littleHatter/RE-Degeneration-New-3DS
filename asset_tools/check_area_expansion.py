"""Check prior-area preservation, intact native files, and replay-bundle equality."""
from pathlib import Path
import argparse,json
from restore import decode,sha

def check(game,prior,inputs,audit,other,report,allow_environment_additions=False):
 override=game/'overrides';previous=prior/'overrides';preserved=[];environment=None
 for p in previous.rglob('*'):
  if not p.is_file():continue
  rel=p.relative_to(previous)
  if rel.as_posix()=='levels/vip/vip.luc':continue
  if allow_environment_additions and rel.as_posix()=='common/environment.group.bin':
   from directory_codec import parse
   old=parse(p.read_bytes());new=parse((override/rel).read_bytes());delta=new.storage_offset-old.storage_offset
   assert new.storage[:len(old.storage)-8]==old.storage[:-8]
   lookup={(r.class_id,r.name_hash):r for r in new.records()}
   for r in old.records():assert lookup[r.class_id,r.name_hash].offset==(r.offset+delta if r.offset else 0)
   environment={'all_prior_storage_bytes_preserved':True,'prior_index_entries_preserved':len(old.records()),'new_index_entries':len(new.records())-len(old.records())}
   continue
  assert p.read_bytes()==(override/rel).read_bytes(),str(rel)
  preserved.append(rel.as_posix())
 inv=json.loads((audit/'inventory.json').read_text());manifest=json.loads((game/'staff_bundle.json').read_text());native=[]
 for r in manifest['files']:
  if not r['category'].startswith('intact original'):continue
  key,e=next((key,e) for key in ['ngage_main','ngage_protected'] for e in inv[key]['entries'] if e['name']==Path(r['path']).name)
  arc='ngage/game/main.dz' if key=='ngage_main' else 'ngage/game/bin/protected.dz.ngdat'
  assert e['decompression']=='valid'
  assert (override/r['path']).read_bytes()==decode((inputs/arc).read_bytes(),e)
  native.append(r['path'])
 for r in manifest['files']:assert sha((override/r['path']).read_bytes())==r['sha256']
 for candidate in other:
  actual={p.relative_to(candidate/'overrides').as_posix() for p in (candidate/'overrides').rglob('*') if p.is_file()}
  expected={p.relative_to(override).as_posix() for p in override.rglob('*') if p.is_file()}
  assert actual==expected
  for rel in expected-{'levels/vip/vip.luc'}:assert (override/rel).read_bytes()==(candidate/'overrides'/rel).read_bytes(),rel
 result={'prior_override_files_byte_identical':preserved,'intact_native_files_byte_identical':native,'manifest_file_hashes_verified':len(manifest['files']),'equivalent_replay_bundles_except_diagnostic_route':len(other)+1,'shared_environment_additions':environment}
 report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['game','prior','inputs','audit','report']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--allow-environment-additions',action='store_true');p.add_argument('--other',type=Path,action='append',default=[]);a=p.parse_args();check(a.game,a.prior,a.inputs,a.audit,a.other,a.report,a.allow_environment_additions)
