from pathlib import Path
import sys,copy,collections,json,struct,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'asset_tools'))
from group_codec import parse,encode,iw_hash
from model_additions import records
from component_codec import read,encode as entencode,Reader
from software_model_codec import read as ngmodel
from restore import decode,sha
from lua_test_route import load
import argparse,tempfile
from audit_archives import inspect
ap=argparse.ArgumentParser(description="Build the BREW full-campaign visual asset trial from prepared version 1.0 game data.")
ap.add_argument('--game',type=Path,required=True);ap.add_argument('--brew-main',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();BASE=args.game
if args.output.exists():raise ValueError('Choose a new output folder; existing data is not overwritten')
EXPECTED={'dutyfreeeast': '72bd9f8e84d449a4203abab4158e73705822884718c85ce5c26a664d4b55cb40', 'dutyfreewest': '1a672ea94a6bc3de9d60f321dd14f8c04631f13599eb676a25417e63bbf5dad8', 'generatortunnels': '7b48be1c5989685433dd4aef3fc51a9d9585cc94733d0e63b3dac0f7035e29aa', 'infirmary': 'e802dc9ec392544860ad4797f7ca0abda2e562830019a3bb7186fadba212004a', 'planecargo': '5a4b0b0c9d9051b4e9ce66e02ac250da83bbf3c954d4812a52bdb6def788fe11', 'planecrashed': 'b228f023b902f4a6c2aaa4306038ae28219aaae3951efc282d54378dc69f2ca0', 'planeentrance': '048bb4def2da2cfd39102a4911f56a327974294dab3217e3622aad790dbced34', 'planeexit': '0b4b17263d86818ea5210e1cdd91aac320fb0d2ff017603ddef2ab6564687ec6', 'security': '68e273103ffe9454d2937bbe27118c213b89d5aeedb754def6113213799611ee', 'staffarea': 'b435615909718bbf69dc5fe8a8245c8ef98af94dc54c84005f174ee9ee8ea575', 'vipplane': 'd86891e114ff6f1ed49308a814365c2f63a76750b2bcf3b20273c13254e715f9', 'warehouse': 'f80e4e675acf9a1ad6581712c88c219db676cd22b10433a7fa73a5d5e548d939'}
for area,digest in EXPECTED.items():
 p=BASE/f'overrides/levels/{area}/{area}.group.bin'
 if sha(p.read_bytes())!=digest:raise ValueError('Game scene differs from the verified version 1.0 profile: '+area)
blob=args.brew_main.read_bytes();inv_brew=inspect(args.brew_main)
if inv_brew['sha256']!='a687a89ce178ca730926d585e031d2afaf60b3424792090fd62c965bd78d1898':raise ValueError('Unsupported BREW archive profile')
work=tempfile.TemporaryDirectory(prefix='re_brew_campaign_');BREW=Path(work.name)
for entry in inv_brew['entries']:
 if entry['path']=='common/environment.group.bin' or any(entry['path']==f'levels/{a}/{a}.group.bin'for a in EXPECTED):
  p=BREW/entry['path'];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(decode(blob,entry))
args.output.mkdir(parents=True);OUT=args.output/'game'
CLASS=iw_hash('CIwEntSpec');render=iw_hash('CIwRenderableModelSpec');collider=iw_hash('CIwColliderSpec');col=iw_hash('CIwModelBlockCols');model=iw_hash('CIwModel');template=0x0e54abcf
A=records((BASE/'overrides/common/environment.group.bin').read_bytes());B=records((BREW/'common/environment.group.bin').read_bytes())
def walk(e):
 for c in e['components']:
  yield c
  if'entity'in c:yield from walk(c['entity'])
def gameplay(e):return [c for c in walk(e)if c.get('class')not in [None,CLASS,render,collider]]
def normal(v):
 if isinstance(v,dict):return {k:(0 if k=='flags'and v.get('class')==col else normal(x))for k,x in v.items()}
 if isinstance(v,list):return list(map(normal,v))
 return v

def template_components(data):
 r=Reader(data,'ngage');flags=r.u8();count=r.u32();out=[{'reference':r.u32()}if i<flags else r.component()for i in range(count)];assert r.pos==len(data);return out
# Literal name references in unchanged game scripts, including native main-archive scripts.
scripts={p.relative_to(BASE/'overrides').as_posix():p.read_bytes()for p in(BASE/'overrides').rglob('*.luc')}
inv=json.loads((Path(__file__).resolve().parents[1]/'asset_tools/native_main_inventory.json').read_text());blob=(BASE/'main.dz').read_bytes()
for entry in inv['entries']:
 if entry['path'].endswith('.luc'):scripts.setdefault(entry['path'],decode(blob,entry))
script_names=collections.defaultdict(set)
def strings(t,path):
 for tag,v in t['constants']:
  if tag==4:
   try:s=v[4:-1].decode('ascii');script_names[iw_hash(s)].add(path)
   except UnicodeDecodeError:pass
 for c in t['children']:strings(c,path)
for path,data in scripts.items():strings(load(data),path)
shutil.copytree(BASE,OUT,dirs_exist_ok=True);reports=[];unresolved=[]
for p in sorted((BASE/'overrides/levels').glob('*/*.group.bin')):
 if '_story.'in p.name or '_mercenary.'in p.name:continue
 rel=p.relative_to(BASE/'overrides');original=p.read_bytes();base=parse(original);source=parse((BREW/rel).read_bytes())
 baseline={r.in_group_hash:read(r.body,'ngage')[0]for r in base.resources()if r.class_id==CLASS};assets={r.in_group_hash:normal(read(r.body,'ngage')[0])for r in source.resources()if r.class_id==CLASS}
 critical={h for h,e in baseline.items()if gameplay(e)};brewcritical={h for h,e in assets.items()if gameplay(e)};assert not brewcritical-critical,(str(rel),'unexpected BREW gameplay entity')
 used_models=set();used_refs=set();resolved=collections.Counter();checked_templates=set()
 def dependencies(c,chain=()):
  if'reference'in c:
   h=c['reference'];assert h not in chain,('template cycle',h);used_refs.add(h);resolved['template_instances']+=1;key=template,h;assert key in A and key in B
   ac=template_components(A[key]);bc=template_components(B[key]);assert normal(ac)==normal(bc),('template differs',hex(h))
   for child in ac:dependencies(child,chain+(h,))
   return
  if c.get('class')==render:
   used_models.add(c['model']);assert(model,c['model'])in A,('missing model',hex(c['model']))
   resolved['renderables']+=1
   if'colors'in c:
    resolved['coloured_renderables']+=1;resolved['colour_entries']+=c['colors']['count'];m=ngmodel(A[model,c['model']]);ind=next(x for x in m['blocks']if x['class']==iw_hash('CIwModelBlockIndGroups'));roles=ind['roles'];stride=sum(x<128 for x in roles);slot=roles[2]
    if slot<128:
     ids=struct.unpack('<'+'H'*(len(ind['indices'])//2),ind['indices']);assert max(ids[slot::stride],default=-1)<c['colors']['count'],('colour index mismatch',hex(c['model']))
  if c.get('class')==collider:resolved['colliders']+=1
  if'entity'in c:
   for child in c['entity']['components']:dependencies(child,chain)
 changed_params=0;retained=[]
 for h,e in list(assets.items()):
  if h in critical:
   aa,bb=gameplay(e),gameplay(baseline[h]);assert[c['class']for c in aa]==[c['class']for c in bb],(str(rel),hex(h),'gameplay class layout differs')
   for new,old in zip(aa,bb):
    if new!=old:
     assert {k:v for k,v in new.items()if k!='extra'}=={k:v for k,v in old.items()if k!='extra'},(str(rel),hex(h),'unexpected gameplay differences');changed_params+=1
    new.clear();new.update(copy.deepcopy(old))
   for key in ['position','quaternion','scale','ids','active','extra']:e[key]=copy.deepcopy(baseline[h][key])
  assert gameplay(e)==gameplay(baseline.get(h,{'components':[]}))
 # Retain baseline-only gameplay entities and any removed object with a known name/reference.
 nonentity=[r.body for r in base.resources()if r.class_id!=CLASS]
 logic_bytes=[entencode(e,'ngage')for h,e in baseline.items()if h in critical]
 for h in baseline.keys()-assets.keys():
  reasons=[]
  if h in critical:reasons.append('baseline gameplay entity')
  if h in script_names:reasons.append('literal script reference')
  if any(struct.pack('<I',h)in data for data in nonentity+logic_bytes):reasons.append('preserved resource/component reference')
  if reasons:assets[h]=copy.deepcopy(baseline[h]);retained.append({'id':f'{h:08x}','reasons':reasons})
 assert critical=={h for h,e in assets.items()if gameplay(e)}
 for h in critical:assert gameplay(assets[h])==gameplay(baseline[h])
 for e in assets.values():
  for c in e['components']:dependencies(c)
 result=copy.deepcopy(base);source_rows={r.in_group_hash:r for r in source.resources()if r.class_id==CLASS};base_rows={r.in_group_hash:r for r in base.resources()if r.class_id==CLASS}
 for section in result.sections:
  for cls in section.classes or []:
   if cls.class_id==CLASS:
    cls.resources=[]
    for h,e in assets.items():
     r=copy.deepcopy(source_rows[h]if h in source_rows else base_rows[h]);r.body=entencode(e,'ngage');assert read(r.body,'ngage')[0]==e;cls.resources.append(r)
 payload=encode(result);check=parse(payload);assert encode(check)==payload
 assert {(r.class_id,r.in_group_hash):r.body for r in base.resources()if r.class_id!=CLASS}=={(r.class_id,r.in_group_hash):r.body for r in check.resources()if r.class_id!=CLASS}
 target=OUT/'overrides'/rel;target.write_bytes(payload)
 row={'area':p.parent.name,'baseline_entities':len(baseline),'new_entities':len(assets),'BREW_entities':len(source_rows),'gameplay_roots_preserved':len(critical),'tested_parameters_preserved':changed_params,'baseline_only_retained':retained,'removed_reconstruction_only_roots':len(baseline.keys()-assets.keys()),'models_verified':len(used_models),'templates_verified':len(used_refs),'resolved':dict(resolved),'nonentity_records_unchanged':True,'before_sha256':sha(original),'after_sha256':sha(payload)};reports.append(row);print(p.parent.name,'OK',dict(resolved),'retained',retained,flush=True)
(args.output/'conversion_checks.json').write_text(json.dumps({'areas':reports,'scripts_checked':len(scripts),'scripts_changed':False,'other_game_files_changed':False},indent=2)+'\n')
