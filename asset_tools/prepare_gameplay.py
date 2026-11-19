"""Prepare all restored areas without either diagnostic story-routing override."""
from pathlib import Path
import argparse,json
from staff_pipeline import build
from warehouse_visibility import apply
from smooth_scene_lighting import smooth

SCENES=['staffarea','planecargo','warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance']
def prepare(inputs,audit,out):
 if out.exists():raise ValueError('choose a fresh output directory')
 game=out/'game';build(inputs,audit,game,True,SCENES[1:]);apply(game,out/'warehouse_visibility.json')
 for scene in SCENES:smooth(game,scene,out/(scene+'_seams.json'))
 manifest=json.loads((game/'staff_bundle.json').read_text());diagnostics={'common/scripts/storymode.luc','levels/vip/vip.luc'}
 for path in diagnostics:(game/'overrides'/path).unlink()
 manifest['files']=[r for r in manifest['files'] if r['path'] not in diagnostics];manifest['diagnostic_only']=False;manifest['test_route']=None;manifest['normal_story_routing']='original archive scripts retained; no diagnostic routing overrides';manifest['full_gameplay_verified']=False
 (game/'staff_bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
 assert len(manifest['files'])==39
 print(json.dumps({'game':str(game),'restored_areas':len(SCENES),'override_files':len(manifest['files']),'normal_story_routing':True,'native_3DS_build_included':False},indent=2))
 return game

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['inputs','audit','out']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();prepare(a.inputs,a.audit,a.out)
