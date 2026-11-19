"""Reproducible, non-destructive Resident Evil donor audit and restoration plan.
No candidate becomes an active runtime override. Python 3.10+, standard library.
"""
import argparse,collections,hashlib,json,lzma,re,struct
from pathlib import Path
from audit_archives import inspect,validate_lua
from group_codec import parse,encode,UnsupportedGroup,CLASS_NAMES,MEMBERS,iw_hash

def sha(b):return hashlib.sha256(b).hexdigest()
def write_json(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def decode(raw,e):
 d=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
 b=d.decompress(raw[e['offset']:],max_length=e['decoded_bytes']+1)
 if not d.eof or sha(b)!=e['decoded_sha256']:raise ValueError('decode differs from audited input')
 return b

def group_info(b,names):
 try:g=parse(b)
 except UnsupportedGroup as e:return {'format':'directory-indexed','typed_reader':'unsupported','reason':str(e)}
 if encode(g)!=b:raise ValueError('group round trip differs')
 resources=g.resources();textures=[]
 for r in resources:
  if r.class_id==iw_hash('CIwTexture'):
   if len(r.body)<23:raise ValueError('short texture header')
   info={'id':f'{r.in_group_hash:08x}','bytes':len(r.body),'prefix_hex':r.body[:32].hex()}
   if r.body[0]==0x14 and r.body[1] in [0x21,0x40,0x41,0x43] and r.body[10] in [9,17,22,23,35]:
    info.update(profile='observed 23-byte header',format_byte=r.body[10],
        width=struct.unpack_from('<H',r.body,13)[0],height=struct.unpack_from('<H',r.body,15)[0])
   else:info['profile']='uninterpreted texture variant'
   textures.append(info)
 members=[]
 for s in g.sections:
  if s.kind==MEMBERS:
   p=s.payload.index(0)+1
   if p+4<=len(s.payload):
    count=struct.unpack_from('<I',s.payload,p)[0]
    members.append({'count_field':count,'remaining_hex':s.payload[p+4:].hex()})
 return {'format':'sectioned','roundtrip':'byte-identical','group_name':g.name,
  'classes':dict(sorted(collections.Counter(names.get(r.class_id,hex(r.class_id)) for r in resources).items())),
  'resource_count':len(resources),'textures':textures,'member_records':members}

def run(inputs,out):
 paths={'ngage_main':inputs/'ngage/game/main.dz','ngage_protected':inputs/'ngage/game/bin/protected.dz.ngdat',
        'ios':inputs/'ios/main.dz','android':inputs/'android/main.dz'}
 reports={k:inspect(p) for k,p in paths.items()};names=dict(CLASS_NAMES)
 name_file=Path(__file__).with_name('class_names.json')
 if name_file.exists():names.update({int(k,16):v for k,v in json.loads(name_file.read_text()).items()})
 catalog=[];objects={};group_stats=collections.Counter();refs=[]
 def store(b):
  h=sha(b);p=out/'objects'/h[:2]/(h+'.bin');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);objects[h]=len(b);return str(p.relative_to(out))
 for source,report in reports.items():
  raw=paths[source].read_bytes()
  for e in report['entries']:
   if e['decompression']!='valid':continue
   b=decode(raw,e);row={'source':source,'path':e['path'],'path_valid':e['path_valid'],'entry_index':e['index'],
     'sha256':sha(b),'bytes':len(b),'kind':e['kind']}
   if e['kind']=='resource group':
    row['group']=group_info(b,names);group_stats[row['group']['format']]+=1
   if source in ['ios','android']:
    row['object']=store(b)
    for script in e.get('embedded_lua',[]):
     chunk=b[script['offset']:script['offset']+script['bytes']];validate_lua(chunk)
     catalog.append({'source':source,'path':script['path'],'path_valid':e['path_valid'],
       'container':e['path'],'container_offset':script['offset'],'sha256':sha(chunk),'bytes':len(chunk),
       'kind':'Lua bytecode','lua_structure':'valid','object':store(chunk)})
   if e['kind']=='Lua bytecode':validate_lua(b);row['lua_structure']='valid'
   # Strings are discovery hints, not a complete dependency graph.
   seen=sorted(set(x.decode('ascii').replace('\\','/').lower() for x in re.findall(
       rb'(?:common|levels)[/\\][A-Za-z0-9_./\\-]+\.(?:group(?:\.bin)?|luc|lua)',b)))
   if seen:refs.append({'source':source,'path':e['path'],'strings':seen,'evidence':'embedded path strings; completeness unverified'})
   catalog.append(row)
 donors=[r for r in catalog if r['source'] in ['ios','android']];rows=[]
 for source in ['ngage_main','ngage_protected']:
  for e in reports[source]['entries']:
   intact=e['decompression']=='valid'
   row={'source':source,'entry_index':e['index'],'original_path':e['path'],
       'path_record_valid':e['path_valid'],'original_integrity':e['decompression'],
       'action':'retain_original' if intact else 'requires_restoration','runtime_accepted':False}
   exact=[d for d in donors if d['path']==e['path'] and d['path_valid']]
   matches=exact or [d for d in donors if Path(d['path']).name==e['name'].lower() and d['path_valid']]
   unique={ (d['source'],d['path'],d['sha256']):d for d in matches }
   row['candidates']=[{k:d[k] for k in ['source','path','sha256','bytes','kind','object'] if k in d}
       |{'match':'exact_path' if exact else 'filename_only','runtime_accepted':False,
         'readiness':'structure_valid_only' if d['kind']=='Lua bytecode' else 'requires_format_conversion'}
       for d in unique.values()]
   row['path_status']='original_table_record' if e['path_valid'] else 'quarantined_pending_path_confirmation'
   if not intact:row['blockers']=['original unavailable','runtime validation missing']+(
      ['resource conversion missing'] if e['name'].endswith('.group.bin') else [])+(
      [] if e['path_valid'] else ['logical path requires independent confirmation'])+(
      [] if matches else ['no donor candidate found'])
   rows.append(row)
 # A directory-wide test set is a conservative batch, not a proven dependency closure.
 batches=[]
 for parent in sorted(set(str(Path(r['original_path']).parent) for r in rows if r['action']=='requires_restoration')):
  members=[r for r in rows if str(Path(r['original_path']).parent)==parent]
  batches.append({'directory':parent,'scope':'directory batch; cross-group dependency closure unverified',
    'members':[r['original_path'] for r in members],
    'shared_resources':'retain every intact common/ resource from original archives',
    'ready_for_activation':False,'blockers':['dependency closure not proven']+
       sorted(set(b for r in members for b in r.get('blockers',[])))})
 summary={'original_entries':len(rows),'intact':sum(r['action']=='retain_original' for r in rows),
   'damaged':sum(r['action']=='requires_restoration' for r in rows),'group_layouts':dict(group_stats),
   'damaged_with_lua_candidates':sum(r['action']=='requires_restoration' and any(c['kind']=='Lua bytecode' for c in r['candidates']) for r in rows),
   'damaged_with_group_candidates':sum(r['action']=='requires_restoration' and any(c['kind']=='resource group' for c in r['candidates']) for r in rows),
   'activated_overrides':0,'stored_objects':len(objects)}
 write_json(out/'inventory.json',reports);write_json(out/'catalog.json',catalog)
 write_json(out/'path_references.json',refs);write_json(out/'restoration_plan.json',{'summary':summary,'entries':rows,'batches':batches})
 write_json(out/'provenance.json',{'inputs':{k:{'sha256':v['sha256'],'bytes':v['bytes']} for k,v in reports.items()},
    'tools':{p.name:sha(p.read_bytes()) for p in sorted(Path(__file__).parent.glob('*.py'))}})
 print(json.dumps(summary,indent=2));return summary
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if a.out.exists():p.error('output must be a new directory')
 run(a.inputs,a.out)
