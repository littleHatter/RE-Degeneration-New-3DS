"""Verify software-quad and external-script profiles against intact game data."""
from pathlib import Path
import argparse,json,struct,collections
from group_codec import parse,iw_hash,UnsupportedGroup
from directory_codec import parse as index_read
from restore import decode
from staff_pipeline import quad_convert,script_convert
from software_model_codec import read as swread,encode as swencode
from model_codec import read as glread

def check(inputs,audit,out):
 inv=json.loads((audit/'inventory.json').read_text());catalog=json.loads((audit/'catalog.json').read_text());records={};stats=collections.Counter()
 for src,relative in [('ngage_main','ngage/game/main.dz'),('ios','ios/main.dz')]:
  e=next(e for e in inv[src]['entries'] if e['path']=='common/environment.group.bin');b=decode((inputs/relative).read_bytes(),e);g=index_read(b);records[src]={(r.class_id,r.name_hash):b[s:t] for r,s,t in g.spans()}
 for (cls,h),body in records['ngage_main'].items():
  if cls!=iw_hash('CIwModel'):continue
  try:model=swread(body)
  except ValueError:continue
  assert swencode(model)==body;stats['software_model_exact_roundtrips']+=1
  other=records['ios'].get((cls,h))
  if not other:continue
  try:
   gl=glread(other);verts=next(b for b in model['blocks'] if b['class']==iw_hash('CIwModelBlockVerts'));bsp=next(b for b in model['blocks'] if b['class']==iw_hash('CIwModelBlockBSP'));ig=next(b for b in model['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'))
   gv=next(b for b in gl['blocks'] if b['class']==iw_hash('CIwModelBlockVerts'))
   if (verts['count'],verts['unique'],gv['count'],gv['unique'])!=(4,4,4,4) or len(bsp['primitives'])!=1 or not bsp['primitives'][0]['flags']&2 or len(model['materials'])!=4:continue
   mh=struct.unpack('<I',model['materials'])[0];material=records['ngage_main'][iw_hash('CIwMaterial'),mh];flags=struct.unpack_from('<I',material,1)[0];converted=swread(quad_convert(other,flags))
  except (ValueError,StopIteration,KeyError):continue
  def positions(v,software):
   raw=v['values'][2:] if software else v['data'];nums=struct.unpack('<12h',raw);return list(zip(nums[:4],nums[4:8],nums[8:]))
  oldpoints=positions(verts,True);newpoints=positions(next(b for b in converted['blocks'] if b['class']==iw_hash('CIwModelBlockVerts')),True);assert sorted(oldpoints)==sorted(newpoints)
  def face(m,points):
   b=next(b for b in m['blocks'] if b['class']==iw_hash('CIwModelBlockBSP'));g=next(b for b in m['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));data=struct.unpack('<8H',g['indices']);ids=struct.unpack('<4H',b['primitives'][0]['indices']);world=[points[data[i*2]] for i in ids];raw=struct.unpack('<8h',b['primitives'][0]['uvs']);stored=list(zip(raw[::2],raw[1::2]));uv=[stored[i] for i in [0,3,1,2]];return world,dict(zip(world,uv)),b['primitives'][0]['flags']
  ow,ou,of=face(model,oldpoints);nw,nu,nf=face(converted,newpoints);assert of==nf
  def edges(w):
   p=[w[i] for i in [0,1,3,2]];return frozenset(tuple(sorted((p[i],p[(i+1)%4]))) for i in range(4))
  assert edges(ow)==edges(nw);stats['quad_geometry_and_primitive_profiles']+=1
  deltas={tuple(ou[p][i]-nu[p][i] for i in range(2)) for p in ou}
  if len(deltas)==1 and all(v%4096==0 for v in next(iter(deltas))):stats['quad_uv_matches_modulo_tiles']+=1
  else:stats['quad_uv_export_differences']+=1
 for src,relative in [('ngage_main','ngage/game/main.dz'),('ngage_protected','ngage/game/bin/protected.dz.ngdat')]:
  raw=(inputs/relative).read_bytes()
  for e in inv[src]['entries']:
   if e.get('kind')!='resource group':continue
   try:g=parse(decode(raw,e))
   except UnsupportedGroup:continue
   for r in g.resources():
    if r.class_id==iw_hash('CIwLuaScriptRes'):
     assert r.body.endswith(b'.luc\0') and b'\0' not in r.body[:-1];assert r.in_group_hash==iw_hash(Path(r.body[:-1].decode()).stem);stats['native_external_script_wrappers']+=1
 for d in catalog:
  if d['source']!='ios' or d['kind']!='resource group':continue
  try:g=parse((audit/d['object']).read_bytes())
  except UnsupportedGroup:continue
  for r in g.resources():
   if r.class_id==iw_hash('CIwLuaScriptRes'):
    b,h,p,c=script_convert(r.body);assert r.in_group_hash==iw_hash(r.body[:r.body.index(0)].decode());stats['donor_embedded_script_wrappers']+=1
 assert stats['quad_geometry_and_primitive_profiles']==153 and stats['quad_uv_matches_modulo_tiles']==150
 assert stats['native_external_script_wrappers']==17 and stats['donor_embedded_script_wrappers']==20
 report={'verified':dict(stats),'scope':'format and geometry profiles; not a full-game or lighting-fidelity claim'};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.inputs,a.audit,a.report)
