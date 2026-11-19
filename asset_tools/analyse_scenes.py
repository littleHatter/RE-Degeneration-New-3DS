"""Reproduce cross-platform class comparisons and a conservative Staff Area plan."""
from pathlib import Path
import argparse,json,collections,struct
from group_codec import parse,encode,UnsupportedGroup,CLASS_NAMES,iw_hash
from restore import decode,sha
from directory_codec import parse as indexed,encode as encode_indexed
from entity_transform import convert,fields

def analyse(inputs,audit,out):
 inventory=json.loads((audit/'inventory.json').read_text());catalog=json.loads((audit/'catalog.json').read_text());names=dict(CLASS_NAMES)
 names.update({int(k,16):v for k,v in json.loads(Path(__file__).with_name('class_names.json').read_text()).items()})
 originals=[];comparisons=[];transforms=[];directory_reports=[];all_models=set();stored_models=set();typed_models=set()
 for source,path in [('ngage_main','ngage/game/main.dz'),('ngage_protected','ngage/game/bin/protected.dz.ngdat')]:
  raw=(inputs/path).read_bytes()
  for e in inventory[source]['entries']:
   if e.get('kind')!='resource group':continue
   data=decode(raw,e)
   try:g=parse(data)
   except UnsupportedGroup:
    g=indexed(data);assert encode_indexed(g)==data
    for r in g.records():
     if r.class_id==iw_hash('CIwModel'):
      all_models.add(r.name_hash)
      if r.offset:stored_models.add(r.name_hash)
    directory_reports.append({'source':source,'path':e['path'],'index_entries':len(g.records()),'stored_records':sum(bool(r.offset) for r in g.records()),'roundtrip':'byte-identical'})
    continue
   assert encode(g)==data
   typed_models.update(r.in_group_hash for r in g.resources() if r.class_id==iw_hash("CIwModel"))
   originals.append((source,e,g))
 for source,e,ng in originals:
  for donor in ['ios','android']:
   matches=[r for r in catalog if r['source']==donor and r['path']==e['path'] and r['kind']=='resource group']
   if len(matches)!=1:continue
   d=parse((audit/matches[0]['object']).read_bytes());dr={(r.class_id,r.in_group_hash):r for r in d.resources()};nr={(r.class_id,r.in_group_hash):r for r in ng.resources()};counts=collections.defaultdict(collections.Counter)
   for key,r in nr.items():
    name=names.get(key[0],hex(key[0]));other=dr.get(key)
    if other is None:counts[name]['missing']+=1
    elif r.body==other.body:counts[name]['identical']+=1
    else:counts[name]['different']+=1;counts[name]['same_length' if len(r.body)==len(other.body) else 'different_length']+=1
    if donor=='ios' and name=='CIwEntSpec' and other is not None and other.body[:5]==b'\0'*5:
     value=convert(other.body);old=fields(r.body);new=fields(value)
     assert all(old[k]==new[k] for k in ['quaternion','identifiers','flags'])
     delta=max(abs(x-y) for x,y in zip(old['position'],new['position']));assert delta<=1
     assert convert(other.body)==value
     try:convert(other.body[:-1])
     except ValueError:pass
     else:raise AssertionError('truncated entity accepted')
     transforms.append({'path':e['path'],'id':r.in_group_hash,'byte_identical':value==r.body,'max_position_delta':delta})
   comparisons.append({'path':e['path'],'donor':donor,'classes':dict(counts),'extra_resources':len(dr.keys()-nr.keys())})
 staff=[]
 for path in ['levels/staffarea/staffarea.group.bin','levels/staffarea/staffarea_story.group.bin']:
  d=next(e for e in catalog if e['source']=='ios' and e['path']==path and e['kind']=='resource group');g=parse((audit/d['object']).read_bytes());counts=collections.Counter();refs=[];unresolved=[]
  for r in g.resources():
   if r.class_id!=iw_hash('CIwEntSpec'):continue
   b=r.body
   if b[:5]==b'\0'*5:
    try:convert(b);counts['convertible_component_free']+=1
    except ValueError:counts['unsupported_component_free']+=1
   else:counts['component_bearing_requires_reader']+=1
   # Verified first component shape only: other entity/component layouts remain uninterpreted.
   if len(b)>54 and b[5:13]==struct.pack('<II',iw_hash('CIwRenderableModelSpec'),iw_hash('CIwVolumeAABox')) and not b[49]&1:
    model=struct.unpack_from('<I',b,50)[0];refs.append(model)
    if model not in stored_models|typed_models:unresolved.append(model)
  script=[r for r in catalog if r['source']=='ios' and r['path']=='levels/staffarea/staffarea.luc' and 'container' in r]
  staff.append({'path':path,'donor_sha256':d['sha256'],'classes':dict(collections.Counter(names.get(r.class_id,hex(r.class_id)) for r in g.resources())),
    'entity_coverage':dict(counts),'first_renderable_model_references':len(refs),'references_to_stored_ngage_environment_models':sum(r in stored_models for r in refs),
    'references_to_any_intact_ngage_model':sum(r in stored_models|typed_models for r in refs),
    'unresolved_first_model_reference_ids':[f'{x:08x}' for x in sorted(set(unresolved))],
    'script_candidates':[{k:r[k] for k in ['path','container','sha256']} for r in script],
    'dependency_closure_proven':False,'ready_for_activation':False,
    'blockers':['component-bearing entity conversion incomplete','all resource references not yet traced','protected logical paths require runtime confirmation','donor-only rendering feature policy unverified']})
 report={'comparison_groups':comparisons,'transform_validation':{'records':len(transforms),'byte_identical':sum(r['byte_identical'] for r in transforms),'maximum_position_delta':max(r['max_position_delta'] for r in transforms),'rotation_identifiers_flags':'identical for every converted pair','truncation_rejected':True,'details':transforms},'original_environment_indices':directory_reports,'staff_area':staff}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({'verified_entity_transforms':len(transforms),'staff_main_entity_coverage':staff[0]['entity_coverage'],'staff_main_model_refs':staff[0]['first_renderable_model_references'],'staff_main_intact_model_refs':staff[0]['references_to_stored_ngage_environment_models']},indent=2));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();analyse(a.inputs,a.audit,a.report)
