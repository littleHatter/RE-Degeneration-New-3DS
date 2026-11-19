"""Verify geometry, intrinsic colors, native primitive controls and texture framing."""
from pathlib import Path
import argparse,json,struct,collections,math
from group_codec import iw_hash,parse as group_parse
from directory_codec import parse
from software_model_codec import read as swread,encode as swencode
from model_codec import read as glread,encode as glencode
from lightmap_bake import points
from model_additions import records
from restore import decode

def check(inputs,audit,game,report):
 inv=json.loads((audit/'inventory.json').read_text());cat=json.loads((audit/'catalog.json').read_text());e=next(e for e in inv['ngage_main']['entries'] if e['path']=='common/environment.group.bin');original=decode((inputs/'ngage/game/main.dz').read_bytes(),e)
 d=next(e for e in cat if e['source']=='ios' and e['path']=='common/environment.group.bin' and 'container' not in e);donor=(audit/d['object']).read_bytes();native=records(original);donors=records(donor);converted=records((game/'overrides/common/environment.group.bin').read_bytes());controls=0
 for (cl,h),body in native.items():
  if cl!=iw_hash('CIwModel'):continue
  try:m=swread(body)
  except ValueError:continue
  for b in m['blocks']:
   if b['class']==iw_hash('CIwModelBlockBSP'):assert b['first']==28*(b['count']+1);controls+=1
 # An intact paired mesh has two independent triangular faces. Normalize each
 # UV axis to remove the platforms' atlas scale/offset while checking ordering.
 h=0x982cc4c5;sm=swread(native[iw_hash('CIwModel'),h]);gm=glread(donors[iw_hash('CIwModel'),h]);sp=points(sm,True);gp=points(gm,False);ig=next(b for b in sm['blocks'] if b['class']==iw_hash('CIwModelBlockIndGroups'));stride=sum(v<128 for v in ig['roles']);ii=struct.unpack('<'+'H'*(len(ig['indices'])//2),ig['indices']);uv=next(b for b in gm['blocks'] if b['class']==iw_hash('CIwModelBlockGLUVs'));us=struct.unpack('<'+'h'*(len(uv['data'])//2),uv['data']);gltris=[]
 for b in gm['blocks']:
  if b['class']!=iw_hash('CIwModelBlockGLTriList'):continue
  ids=struct.unpack('<'+'H'*b['count'],b['data']);gltris.extend(ids[i:i+3] for i in range(0,len(ids),3))
 def norm(pairs):
  lo=[min(p[k] for p in pairs) for k in range(2)];hi=[max(p[k] for p in pairs) for k in range(2)]
  return [[(p[k]-lo[k])/(hi[k]-lo[k]) if hi[k]!=lo[k] else 0 for k in range(2)] for p in pairs]
 triangles=0
 for b in sm['blocks']:
  if b['class']!=iw_hash('CIwModelBlockBSP'):continue
  for p in b['primitives']:
   if p['flags']&(2|0x10000):continue
   ids=struct.unpack('<3H',p['indices']);xyz=[sp[ii[i*stride+ig['roles'][0]]] for i in ids];source=next(t for t in gltris if set(gp[i] for i in t)==set(xyz));opposite=[gp[source[0]],gp[source[2]],gp[source[1]]];assert any(xyz==opposite[k:]+opposite[:k] for k in range(3))
   puv=list(zip(*[iter(struct.unpack('<8h',p['uvs']))]*2));actual=norm([puv[i] for i in [0,2,1]]);expected=norm([us[i*2:i*2+2] for v in xyz for i in source if gp[i]==v]);assert actual==expected;triangles+=1
 assert triangles==2
 rows=[]
 for h in [0x06ea0764,0xbd964f5e,0x9ae20780]:
  key=(iw_hash('CIwModel'),h);g=glread(donors[key]);s=swread(converted[key]);assert glencode(g)==donors[key];assert swencode(s)==converted[key];assert points(g,False)==points(s,True);assert g['materials']==s['materials'];source=[];target=[]
  for b in g['blocks']:
   if b['class']==iw_hash('CIwModelBlockGLTriList'):
    ids=struct.unpack('<'+'H'*b['count'],b['data']);source.extend((b['material'],tuple(ids[i:i+3])) for i in range(0,len(ids),3))
  for b in s['blocks']:
   if b['class']==iw_hash('CIwModelBlockBSP'):
    assert not b['nodes'] and b['links']==struct.pack('<I',b['count']<<16)
    for p in b['primitives']:
     a,c,b0=struct.unpack('<3H',p['indices']);target.append((b['material'],(a,b0,c)))
  assert collections.Counter(source)==collections.Counter(target)
  gc=[b['colors'] for b in g['blocks'] if b['class']==iw_hash('CIwModelBlockCols')];sc=[b['colors'] for b in s['blocks'] if b['class']==iw_hash('CIwModelBlockCols')];assert gc==sc
  rows.append({'model':f'{h:08x}','vertices':len(points(s,True)),'triangles':len(source),'geometry_material_references_and_model_colors_preserved':True,'both_format_roundtrips':True})
 tex=converted[iw_hash('CIwTexture'),0x43dd0f05];w,h=struct.unpack_from('<HH',tex,13);assert (w,h)==(128,128) and tex[0]==0x14 and tex[10]==22 and len(tex)==23+w*h//2+33 and tex[-1]==0;assert all(v&0x8000 for v in struct.unpack('<16H',tex[-33:-1]));assert struct.unpack_from('<H',tex,17)[0]==w//2
 result={'native_BSP_allocation_controls':controls,'native_triangle_winding_and_UV_controls':triangles,'converted_models':rows,'new_texture_native_framing_and_opaque_palette':'passed'};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['inputs','audit','game','report']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();check(a.inputs,a.audit,a.game,a.report)
