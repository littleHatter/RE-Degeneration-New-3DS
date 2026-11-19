"""Replay original/converted component controls and report timing-sensitive frames."""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess
from build_component_control import build
from restore import sha

def evaluate(probe,out):
 results=[]
 for case in ['original','converted']:
  folder=out/case;text=(folder/'runtime.log').read_text(errors='replace');m=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',text)
  assert m and m.groups()==('0','900','0'),'scene control did not complete successfully'
  assert (folder/'frames/frame_000900.ppm').is_file(),'missing final frame'
  results.append({'case':case,'runtime_result':0,'frames':900,'failed':False})
 target_path=out/'converted/game/overrides/levels/vip/vip.group.bin';target=target_path.read_bytes();control=json.loads(target_path.with_suffix(target_path.suffix+'.json').read_text());assert sha(target)==control['output_sha256'],'control content changed'
 capture=(out/'converted/trace/stream_0002.bin').read_bytes();assert capture==target,'consumed override differs'
 same=(out/'original/frames/frame_000900.ppm').read_bytes()==(out/'converted/frames/frame_000900.ppm').read_bytes()
 report={'all_override_bytes_verified':True,'override_sha256':sha(target),'runtime_sha256':sha(probe.read_bytes()),
  'runs':results,'converted_records':control['statistics']['converted_entities'],'component_bearing_records':control['statistics']['component_bearing_converted'],
  'final_frame_identical':same,'visual_regression_verdict':'not established; wall-clock caption timing differs between runs',
  'scope':control['scope'],'damaged_scene_restored':False,'runtime_loader_checks':'passed'}
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return report

def main(inputs,audit,probe,input_script,out):
 if out.exists():raise ValueError('choose a new output directory')
 for case in ['original','converted']:
  folder=out/case;game=folder/'game';shutil.copytree(inputs/'ngage/game',game)
  if case=='converted':build(inputs,audit,'levels/vip/vip.group.bin',game/'overrides/levels/vip/vip.group.bin')
  env=dict(os.environ,RE_HYBRID_RESOURCE='levels/vip/vip.group.bin')
  for key in ['RE_HYBRID_TRACE','RE_STREAM_TEST','RE_STREAM_REFERENCE']:env.pop(key,None)
  if case=='converted':env['RE_HYBRID_TRACE']=str((folder/'trace').resolve())
  with (folder/'runtime.log').open('w') as log:
   p=subprocess.run([str(probe.resolve()),str(game.resolve()),'900',str((folder/'frames').resolve()),str((folder/'user').resolve()),str(input_script.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
  assert p.returncode==0,'runtime did not exit successfully'
 return evaluate(probe,out)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--input-script',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--check-existing',action='store_true',help='validate completed run evidence without executing the game again');a=p.parse_args()
 if a.check_existing:evaluate(a.probe,a.out)
 else:main(a.inputs,a.audit,a.probe,a.input_script,a.out)
