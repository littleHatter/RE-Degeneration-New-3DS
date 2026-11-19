"""Check preservation, prior scene regressions and color bounds in a four-area batch."""
from pathlib import Path
import argparse,json,collections
from group_codec import parse,iw_hash
from component_codec import read
from color_contract import ColorContract

def check(game,prior_staff,prior_cargo,report,inputs,audit):
 contract=ColorContract((game/'overrides/common/environment.group.bin').read_bytes());counts=collections.Counter()
 def scan(e):
  for c in e['components']:
   if 'entity' in c:scan(c['entity'])
   if c.get('class')==iw_hash('CIwRenderableModelSpec') and 'colors' in c:
    assert c['colors']['count']>=contract.required[c['model']];counts['color_arrays_checked']+=1
 for p in (game/'overrides/levels').glob('*/*.group.bin'):
  for r in parse(p.read_bytes()).resources():
   if r.class_id==iw_hash('CIwEntSpec'):scan(read(r.body,'ngage')[0]);counts['entities_parsed_including_intact_groups']+=1
 for scene,prior in [('staffarea',prior_staff),('planecargo',prior_cargo)]:
  for suffix in ['', '_story']:
   p=f'overrides/levels/{scene}/{scene}{suffix}.group.bin';assert (game/p).read_bytes()==(prior/p).read_bytes()
 for scene in ['warehouse','planecrashed']:assert (game/f'overrides/levels/{scene}/{scene}_story.group.bin').exists()
 assert (game/'overrides/levels/planecrashed/planecrashed.luc').exists()
 assert (game/'overrides/levels/warehouse/warehouse.luc').exists()
 from restore import decode
 inv=json.loads((audit/'inventory.json').read_text())
 preserved=[]
 for path in ['levels/warehouse/warehouse_story.group.bin','levels/planecrashed/planecrashed_story.group.bin','levels/planecrashed/planecrashed.luc']:
  src,e=next((src,e) for src in ['ngage_main','ngage_protected'] for e in inv[src]['entries'] if e['name']==Path(path).name)
  arc='ngage/game/main.dz' if src=='ngage_main' else 'ngage/game/bin/protected.dz.ngdat'
  assert (game/'overrides'/path).read_bytes()==decode((inputs/arc).read_bytes(),e)
  preserved.append(path)
 result={'preserved_original_bodies_byte_identical':preserved,'counts':dict(counts),'prior_staff_and_cargo_scene_groups_byte_identical':True,'intact_story_groups_externalized':True,'intact_planecrashed_script_externalized':True,'damaged_warehouse_script_externalized':True};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game',type=Path,required=True);p.add_argument('--prior-staff',type=Path,required=True);p.add_argument('--prior-cargo',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);a=p.parse_args();check(a.game,a.prior_staff,a.prior_cargo,a.report,a.inputs,a.audit)
