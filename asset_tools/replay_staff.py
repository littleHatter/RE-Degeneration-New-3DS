"""Build and replay a complete Staff Area diagnostic bundle in an isolated save tree."""
from pathlib import Path
import argparse,json,os,re,subprocess
from staff_pipeline import build
from restore import sha

def run(inputs,audit,probe,out,frames,lighting=False,smoothing=False):
 if out.exists():raise ValueError('choose a new output directory')
 game=out/'game';manifest=build(inputs,audit,game,lighting)
 if smoothing:
  if not lighting:raise ValueError('smoothing requires approximate lighting')
  from smooth_scene_lighting import smooth
  smooth(game,'staffarea',out/'shared_edge_lighting.json')
 lines=''.join(f'{f} {f+3} 208\n' for f in range(200,800,60))
 lines+='1000 1002 76\n1050 1200 204\n1230 1290 207\n1320 1440 204\n1500 1560 206\n1600 1720 204\n'
 script=out/'input.txt';script.write_text(lines);env=dict(os.environ,RE_TEST_ROUTE='staffarea',RE_HYBRID_BUNDLE='staffarea',RE_HYBRID_RESOURCE='common/environment.group.bin',RE_HYBRID_TRACE=str((out/'trace').resolve()))
 env['RE_AUDIO_CAPTURE']=str((out/'audio.wav').resolve())
 for key in ['RE_STREAM_TEST','RE_STREAM_REFERENCE']:env.pop(key,None)
 with (out/'runtime.log').open('w') as log:
  result=subprocess.run([str(probe.resolve()),str(game.resolve()),str(frames),str((out/'frames').resolve()),str((out/'user').resolve()),str(script.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 text=(out/'runtime.log').read_text(errors='replace');m=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',text)
 required=['levels/staffarea/staffarea.group.bin','levels/staffarea/staffarea_story.group.bin','levels/staffarea/staffarea.luc']
 opened={p:p in re.findall(r'\[S3E\] Open ([^\n]+)',text) for p in required}
 report={'runtime_sha256':sha(probe.read_bytes()),'runtime_exit':result.returncode,'summary':m.group(0) if m else None,'required_staff_resources_opened':opened,'frames':int(m[2]) if m else None,'diagnostic_lighting':True,'shared_edge_lighting':smoothing,'lighting':manifest['lighting'],'full_game_restored':False,'input_script_sha256':sha(script.read_bytes())}
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 if result.returncode!=0 or not m or m.groups()!=('0',str(frames),'0') or not all(opened.values()):raise RuntimeError('Staff Area diagnostic did not complete; inspect results/log')
 print(json.dumps(report,indent=2));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=1450);p.add_argument('--approximate-lighting',action='store_true');p.add_argument('--smooth-lighting',action='store_true');a=p.parse_args();run(a.inputs,a.audit,a.probe,a.out,a.frames,a.approximate_lighting,a.smooth_lighting)
