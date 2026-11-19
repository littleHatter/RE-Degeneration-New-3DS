"""Reproduce Staff Area and an optional validated Plane Cargo desktop batch.
This does not claim original lighting fidelity or a restored full game.
"""
from pathlib import Path,PurePosixPath
import argparse,json,struct,copy,collections,shutil
from group_codec import parse,encode as group_encode,iw_hash
from directory_codec import parse as index_read,encode as index_encode,IndexRecord
from component_codec import read as entity_read,encode as entity_encode,u32,Unsupported
from restore import decode,sha
from audit_archives import validate_lua
from model_codec import read as graphics_model
from software_model_codec import read as software_model,encode as software_encode
from lua_test_route import skip_intro,staff_route
from color_contract import ColorContract

MATERIAL_FLAGS={0x50009:0x10e,0x1:0x10e,0x50001:0x10e,0x30001:0x70e,0x20001:0x50e}
MODEL_IDS=[0xa157664e,0xa157664f,0xa1576655]
def quad_convert(body,material_flags):
 source=graphics_model(body);blocks={b['class']:b for b in source['blocks']};keys=[iw_hash(n) for n in ['CIwModelBlockVerts','CIwModelBlockGLUVs','CIwModelBlockGLTriList']]
 if any(k not in blocks for k in keys) or len(source['materials'])!=4:raise Unsupported('quad profile')
 v,uv,tri=[blocks[k] for k in keys]
 if (v['count'],v['unique'],uv['count'],tri['count'])!=(4,4,4,6):raise Unsupported('quad vertex/triangle count')
 if set(blocks)-set(keys)-{iw_hash('CIwModelBlockGLUVs2')}:raise Unsupported('additional model blocks')
 ind=struct.unpack('<6H',tri['data']);a,b,c=ind[:3]
 if ind[3:5]!=(a,c) or set(ind)!={0,1,2,3} or tri['material']!=0:raise Unsupported('quad topology')
 if material_flags not in MATERIAL_FLAGS:raise Unsupported('primitive material profile')
 order=(b,a,c,ind[5]);primary=struct.unpack('<8h',uv['data']);pairs=[primary[i*2:i*2+2] for i in order];encoded_uv=tuple(x for i in [0,2,3,1] for x in pairs[i])
 vb=dict(**{k:v[k] for k in ['class','name','first','count','flags','unique']},values=struct.pack('<H',v['packing'])+v['data'])
 ig=dict(class_=iw_hash('CIwModelBlockIndGroups'),name=iw_hash('CIwModelBlockIndGroups'),first=0,count=4,flags=0,roles=bytes([0,255,1]),indices=struct.pack('<8H',0,0,1,1,2,2,3,3));ig['class']=ig.pop('class_')
 primitive=dict(flags=MATERIAL_FLAGS[material_flags],indices=struct.pack('<4H',*order),uvs=struct.pack('<8h',*encoded_uv))
 bsp={'class':iw_hash('CIwModelBlockBSP'),'name':iw_hash('CIwModelBlockBSP'),'first':56,'count':1,'flags':0,'material':0,'points':struct.pack('<4H',*order),'primitives':[primitive],'nodes':b'','links':u32(1<<16)}
 if struct.unpack_from('<I',source['header'])[0] not in [0,0x1000000]:raise Unsupported('graphics model flags')
 target=dict(header=u32(0x80000)+source['header'][4:],blocks=[vb,ig,bsp],materials=source['materials']);out=software_encode(target);assert software_encode(software_model(out))==out;return out

def append_resources(data,additions):
 original=index_read(data);g=copy.deepcopy(original);existing={(r.class_id,r.name_hash) for r in g.records()}
 if len(set((c,n) for c,n,b in additions))!=len(additions) or any((c,n) in existing for c,n,b in additions):raise ValueError('resource collision')
 delta=len(additions)*8;g.storage_offset+=delta
 for r in g.records():
  if r.offset:r.offset+=delta
 classes={c:rows for c,rows in g.classes};storage=bytearray(g.storage[:-8])
 for c,n,b in additions:
  if c not in classes:raise Unsupported('new indexed class')
  classes[c].append(IndexRecord(c,n,g.storage_offset+len(storage)));storage+=struct.pack('<II',c,n)+b
 g.storage=bytes(storage)+b'\0'*8;out=index_encode(g);parsed=index_read(out);assert parsed.storage[:len(original.storage)-8]==original.storage[:-8]
 lookup={(r.class_id,r.name_hash):r for r in parsed.records()}
 for r in original.records():assert lookup[r.class_id,r.name_hash].offset==(r.offset+delta if r.offset else 0)
 return out

def script_convert(body):
 end=body.index(0);source=body[:end].decode('ascii').replace('\\','/')
 if not source.endswith('.lua') or '..' in PurePosixPath(source).parts:raise Unsupported('embedded script path')
 chunk=body[end+5:];assert struct.unpack_from('<I',body,end+1)[0]==len(chunk);validate_lua(chunk);path=source[:-4]+'.luc'
 return path.encode()+b'\0',iw_hash(PurePosixPath(source).stem),path.lower(),chunk

def build(inputs,audit,out,lighting=False,extra_scene=None):
 inv=json.loads((audit/'inventory.json').read_text());catalog=json.loads((audit/'catalog.json').read_text());stats=collections.Counter();files=[]
 def archive_resource(key,relative,path):
  e=next(e for e in inv[key]['entries'] if e['path']==path);return decode((inputs/relative).read_bytes(),e)
 def donor(path):
  d=next(e for e in catalog if e['source']=='ios' and e['path']==path and 'container' not in e);b=(audit/d['object']).read_bytes();assert sha(b)==d['sha256'];return b
 def save(path,b,category):
  p=out/'overrides'/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);files.append({'path':path,'sha256':sha(b),'bytes':len(b),'category':category})
 # Preserve the complete original environment; add only converted missing records.
 native=archive_resource('ngage_main','ngage/game/main.dz','common/environment.group.bin');ios=donor('common/environment.group.bin');ig=index_read(ios);records={(r.class_id,r.name_hash):ios[s:e] for r,s,e in ig.spans()}
 mat=records[iw_hash('CIwMaterial'),0xf5aecebe];assert mat==bytes.fromhex('0181000200ae2b8522');additions=[(iw_hash('CIwMaterial'),0xf5aecebe,bytes.fromhex('0101000200ae2b8522'))]
 for material_id in [0x26a22c1f,0x4c565c65]:
  assert records[iw_hash('CIwMaterial'),material_id]==mat
  additions.append((iw_hash('CIwMaterial'),material_id,bytes.fromhex('0101000200ae2b8522')))
 for h in MODEL_IDS:additions.append((iw_hash('CIwModel'),h,quad_convert(records[iw_hash('CIwModel'),h],0x20001)))
 new_models=None
 requested=[] if extra_scene is None else [extra_scene] if isinstance(extra_scene,str) else list(extra_scene)
 if any(s in requested for s in ['security','planeentrance']):
  from model_additions import additions as missing_additions
  fixed=archive_resource('ngage_main','ngage/game/main.dz','common/fixed_wav.group.bin')
  more,new_models=missing_additions(native,ios,fixed);additions+=more
 environment=append_resources(native,additions);contract=ColorContract(environment)
 baker=None
 if lighting:
  from lightmap_bake import LightmapBake
  baker=LightmapBake(environment,ios)
 story_repairs=[]
 save('common/environment.group.bin',environment,'converted shared additions')
 scenes=['staffarea']
 extras=[] if extra_scene is None else [extra_scene] if isinstance(extra_scene,str) else list(extra_scene)
 if len(set(extras))!=len(extras) or any(x not in ['planecargo','warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance'] for x in extras):raise Unsupported('unvalidated additional scene')
 scenes+=extras
 native_entries={e['name']:e for key in ['ngage_main','ngage_protected'] for e in inv[key]['entries']}
 def intact_bytes(name):
  key,entry=next((key,e) for key in ['ngage_main','ngage_protected'] for e in inv[key]['entries'] if e['name']==name)
  arc='ngage/game/main.dz' if key=='ngage_main' else 'ngage/game/bin/protected.dz.ngdat'
  return decode((inputs/arc).read_bytes(),entry)
 def extract_script(resource):
  body,h,p,chunk=script_convert(resource.body)
  original=native_entries.get(PurePosixPath(p).name)
  if original is None:raise Unsupported('script absent from original archive directory')
  if original['decompression']=='invalid':
   candidate=next(e for e in catalog if e['source']=='ios' and e['path']==p and 'container' in e);assert chunk==(audit/candidate['object']).read_bytes();save(p,chunk,'extracted external script')
  elif PurePosixPath(p).parent.name in ['warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance']:
   save(p,intact_bytes(PurePosixPath(p).name),'intact original script externalized')
  return body,h
 paths=[f'levels/{scene}/{scene}{suffix}.group.bin' for scene in scenes for suffix in (['', '_story', '_mercenary'] if scene=='dutyfreeeast' else ['', '_story'])]
 for path in paths:
  g=parse(donor(path));g.header=bytes.fromhex('3d0305060000')
  original=native_entries.get(PurePosixPath(path).name)
  if original is None:raise Unsupported('group absent from original archive directory')
  if original['decompression']=='valid':
   original_body=intact_bytes(original['name'])
   if path=='levels/security/security_story.group.bin':
    from story_color_bounds import repair
    original_body,story_repairs=repair(original_body,environment);save(path,original_body,'native story with color bounds repair')
   else:save(path,original_body,'intact original group externalized')
   for r in g.resources():
    if r.class_id==iw_hash('CIwLuaScriptRes'):extract_script(r)
   stats['intact_groups_externalized']+=1
   continue
  if baker:
   baker.coarse_surface_projection=path=='levels/staffarea/staffarea.group.bin'
   textures=[r.body for r in g.resources() if r.class_id==iw_hash('CIwTexture')]
   if textures:
    if len(textures)!=1:raise Unsupported('scene lightmap selection')
    baker.atlas(textures[0],'repeat' if path.split('/')[1] in ['warehouse','planecrashed','generatortunnels','planeexit','dutyfreewest','security','planeentrance'] else 'clamp')
  for section in g.sections:
   if section.classes is None:continue
   section.classes=[c for c in section.classes if c.class_id!=iw_hash('CIwTexture')]
   for cls in section.classes:
    for r in cls.resources:
     if r.class_id==iw_hash('CIwEntSpec'):
      entity,_=entity_read(r.body,'ios');assert entity_encode(entity,'ios')==r.body
      bake_row_start=len(baker.rows) if baker else 0
      def unlit(e):
       for c in e['components']:
        if 'entity' in c:unlit(c['entity'])
        if c.get('class')!=iw_hash('CIwRenderableModelSpec'):continue
        if 'lightmap_uvs' in c and not (baker and baker.bake(c)):
         n=c['lightmap_uvs']['count'];old=c.get('colors');colors=old['colors'] if old else b'\xff'*(n*4)
         if len(colors)!=n*4:raise Unsupported('color/UV counts')
         c['flags']|=2;c['colors']={'class':iw_hash('CIwModelBlockCols'),'first':old['first'] if old else 44,'count':n,'flags':0,'mode':0,'colors':colors};stats['renderables']+=1;stats['vertices']+=n;stats['new_color_blocks']+=old is None
        contract.ensure(c,stats)
      unlit(entity)
      if baker:
       for row in baker.rows[bake_row_start:]:row.update(scene=path,entity=f'{r.in_group_hash:08x}')
      r.body=entity_encode(entity,'ngage',True);assert entity_encode(entity_read(r.body,'ngage')[0],'ngage')==r.body;stats['entities']+=1
     elif r.class_id==iw_hash('CIwLuaScriptRes'):
      body,h=extract_script(r);r.body=body;r.in_group_hash=h
      if r.name_hash is not None:r.name_hash=h
      stats['external_script_wrappers']+=1
  payload=group_encode(g);assert group_encode(parse(payload))==payload;save(path,payload,'converted scene')
 # Separate diagnostic routing from restoration resources.
 story=archive_resource('ngage_main','ngage/game/main.dz','common/scripts/storymode.luc');vip=archive_resource('ngage_main','ngage/game/main.dz','levels/vip/vip.luc')
 save('common/scripts/storymode.luc',skip_intro(story),'test route only');save('levels/vip/vip.luc',staff_route(vip),'test route only')
 shutil.copytree(inputs/'ngage/game',out,dirs_exist_ok=True)
 result={'diagnostic_only':True,'lighting':'sampled donor lightmap approximation' if lighting else 'unlit; fidelity not restored','statistics':dict(stats),'files':files,'staff_area_fully_restored':False,'included_scene_batches':scenes,'test_route':'native Level.Load(staffArea, leonspawn)','original_archive_hashes':{k:v['sha256'] for k,v in inv.items()},'known_limits':['lighting fidelity','limited movement/collision coverage','four other donor-only model variants outside this scene']}
 if new_models:result['model_additions']=new_models
 if story_repairs:result['native_story_color_repairs']=story_repairs
 if baker:result['lightmap_bake']={'statistics':dict(baker.stats),'instances':baker.rows,'sampling':'bilinear, UV/4096, no vertical inversion; clamp borders; exact geometry preferred; bounded material/surface-filtered nearest neighbors; average shared color slots'}
 out.mkdir(parents=True,exist_ok=True);(out/'staff_bundle.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'statistics':dict(stats),'bundle_files':len(files)},indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--approximate-lighting',action='store_true');p.add_argument('--extra-scene',choices=['planecargo','warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance'],action='append');a=p.parse_args();build(a.inputs,a.audit,a.out,a.approximate_lighting,a.extra_scene)
