"""Build Staff + Plane Cargo restoration batches and probe Plane Cargo in isolation."""
from pathlib import Path
import argparse,json,os,re,subprocess
from staff_pipeline import build
from restore import decode,sha
from lua_test_route import staff_route

def run(inputs,audit,probe,out,frames,seams=False):
 if out.exists():raise ValueError('choose a fresh output directory')
 game=out/'game';manifest=build(inputs,audit,game,True,'planecargo')
 inv=json.loads((audit/'inventory.json').read_text());e=next(e for e in inv['ngage_main']['entries'] if e['path']=='levels/vip/vip.luc');original=decode((inputs/'ngage/game/main.dz').read_bytes(),e);route=staff_route(original,'planeCargo');(game/'overrides/levels/vip/vip.luc').write_bytes(route)
 for r in manifest['files']:
  if r['path']=='levels/vip/vip.luc':r.update(sha256=sha(route),bytes=len(route),category='Plane Cargo diagnostic route only')
 manifest['test_route']='native Level.Load(planeCargo, leonspawn) via test-only VIP event handler';(game/'staff_bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
 if seams:
  from smooth_scene_lighting import smooth
  smooth(game,'planecargo',out/'shared_edge_lighting.json')
 script=out/'input.txt';script.write_text(''.join(f'{f} {f+3} 208\n' for f in range(200,800,60))+'1000 1002 76\n1050 1120 204\n1200 1240 207\n1260 1340 204\n')
 env=dict(os.environ,RE_TEST_ROUTE='staffarea',RE_HYBRID_BUNDLE='staffarea',RE_HYBRID_RESOURCE='common/environment.group.bin',RE_AUDIO_CAPTURE=str((out/'audio.wav').resolve()))
 for k in ['RE_STREAM_TEST','RE_STREAM_REFERENCE','RE_HYBRID_TRACE']:env.pop(k,None)
 with (out/'runtime.log').open('w') as log:r=subprocess.run([str(probe.resolve()),str(game.resolve()),str(frames),str((out/'frames').resolve()),str((out/'user').resolve()),str(script.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
 text=(out/'runtime.log').read_text(errors='replace');m=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',text);paths=[f'levels/planecargo/planecargo{s}' for s in ['.group.bin','_story.group.bin','.luc']];opened=re.findall(r'\[S3E\] Open ([^\n]+)',text)
 result={'runtime_exit':r.returncode,'summary':m.group(0) if m else None,'required_resources':{p:p in opened for p in paths},'runtime_sha256':sha(probe.read_bytes()),'input_sha256':sha(script.read_bytes()),'shared_edge_lighting':seams,'diagnostic_route_only':True,'normal_story_progression_verified':False,'full_game_restored':False}
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 if r.returncode or not m or m.groups()!=('0',str(frames),'0') or not all(result['required_resources'].values()):raise RuntimeError('Plane Cargo test failed; inspect results')
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=1800);p.add_argument('--smooth-lighting',action='store_true');a=p.parse_args();run(a.inputs,a.audit,a.probe,a.out,a.frames,a.smooth_lighting)
