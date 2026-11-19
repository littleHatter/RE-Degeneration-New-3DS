"""Build four restored-area batches and replay one new area in an isolated save tree."""
from pathlib import Path
import argparse,json,os,re,subprocess
from staff_pipeline import build
from lua_test_route import staff_route
from smooth_scene_lighting import smooth
from restore import decode,sha

def run(inputs,audit,probe,out,area,frames,visibility=False):
 if out.exists():raise ValueError('choose a fresh output directory')
 names={'warehouse':'warehouse','planecrashed':'planeCrashed','generatortunnels':'generatorTunnels','infirmary':'infirmary','planeexit':'planeExit','dutyfreewest':'dutyFreeWest','dutyfreeeast':'dutyFreeEast','vipplane':'vipPlane','security':'security','planeentrance':'planeEntrance'}
 if area not in names:raise ValueError('unvalidated target')
 game=out/'game';manifest=build(inputs,audit,game,True,['planecargo','warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance']);inv=json.loads((audit/'inventory.json').read_text());e=next(e for e in inv['ngage_main']['entries'] if e['path']=='levels/vip/vip.luc');original=decode((inputs/'ngage/game/main.dz').read_bytes(),e);route=staff_route(original,names[area]);(game/'overrides/levels/vip/vip.luc').write_bytes(route)
 for r in manifest['files']:
  if r['path']=='levels/vip/vip.luc':r.update(sha256=sha(route),bytes=len(route),category=f'{area} diagnostic route only')
 manifest['test_route']=f'native Level.Load({names[area]}, leonspawn) via diagnostic VIP handler';(game/'staff_bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
 if visibility:
  from warehouse_visibility import apply
  apply(game,out/'warehouse_visibility.json')
 for scene in ['staffarea','planecargo','warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance']:smooth(game,scene,out/f'{scene}_seams.json')
 script=out/'input.txt';script.write_text(''.join(f'{f} {f+3} 208\n' for f in range(200,800,60))+'1000 1002 76\n1050 1120 204\n1200 1240 207\n1260 1340 204\n')
 env=dict(os.environ,RE_TEST_ROUTE='staffarea',RE_HYBRID_BUNDLE='staffarea',RE_HYBRID_RESOURCE='common/environment.group.bin',RE_AUDIO_CAPTURE=str((out/'audio.wav').resolve()))
 for k in ['RE_HYBRID_TRACE','RE_STREAM_TEST','RE_STREAM_REFERENCE']:env.pop(k,None)
 with (out/'runtime.log').open('w') as log:r=subprocess.run([str(probe.resolve()),str(game.resolve()),str(frames),str((out/'frames').resolve()),str((out/'user').resolve()),str(script.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 text=(out/'runtime.log').read_text(errors='replace');m=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',text);paths=[f'levels/{area}/{area}{s}' for s in ['.group.bin','_story.group.bin','.luc']];opened=re.findall(r'\[S3E\] Open ([^\n]+)',text)
 report={'area':area,'runtime_exit':r.returncode,'summary':m.group(0) if m else None,'required_resources':{p:p in opened for p in paths},'runtime_sha256':sha(probe.read_bytes()),'input_sha256':sha(script.read_bytes()),'warehouse_visibility':visibility,'diagnostic_route_only':True,'normal_mission_progression_verified':False,'full_game_restored':False};(out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 if r.returncode or not m or m.groups()!=('0',str(frames),'0') or not all(report['required_resources'].values()):raise RuntimeError('area replay failed; inspect log/result')
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--area',choices=['warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance'],required=True);p.add_argument('--frames',type=int,default=1800);p.add_argument('--warehouse-visibility',action='store_true');a=p.parse_args();run(a.inputs,a.audit,a.probe,a.out,a.area,a.frames,a.warehouse_visibility)
