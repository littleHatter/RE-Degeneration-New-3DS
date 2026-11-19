"""Automated original/converted-entity scene replay, with separate data and saves."""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess
from scene_control import build
from restore import sha

def main(inputs,audit,probe,input_script,out):
 if out.exists():raise ValueError('choose a new output directory')
 results=[]
 inventory=json.loads((audit/'inventory.json').read_text());catalog=json.loads((audit/'catalog.json').read_text())
 for case in ['original','converted']:
  folder=out/case;game=folder/'game';shutil.copytree(inputs/'ngage/game',game)
  if case=='converted':control=build(inputs,inventory,catalog,audit,game/'overrides/levels/vip/vip.group.bin')
  env=dict(os.environ,RE_HYBRID_RESOURCE='levels/vip/vip.group.bin')
  for key in ['RE_HYBRID_TRACE','RE_STREAM_TEST','RE_STREAM_REFERENCE']:env.pop(key,None)
  if case=='converted':env['RE_HYBRID_TRACE']=str((folder/'trace').resolve())
  with (folder/'runtime.log').open('w') as log:
   p=subprocess.run([str(probe.resolve()),str(game.resolve()),'900',str((folder/'frames').resolve()),str((folder/'user').resolve()),str(input_script.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=90)
  text=(folder/'runtime.log').read_text(errors='replace');m=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',text)
  assert p.returncode==0 and m and m.groups()==('0','900','0'),'scene control did not complete successfully'
  results.append({'case':case,'exit_code':p.returncode,'frames':900,'failed':False})
 first=(out/'original/frames/frame_000900.ppm').read_bytes();second=(out/'converted/frames/frame_000900.ppm').read_bytes()
 # This checkpoint uses the same timed story screen as a reproducible final-state control.
 assert first==second,'final control frame changed; inspect evidence'
 report={'runtime_sha256':sha(probe.read_bytes()),'runs':results,'converted_records':control['converted_entities'],
  'final_frame_identical':True,'scope':control['scope'],'damaged_scene_restored':False}
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--input-script',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.inputs,a.audit,a.probe,a.input_script,a.out)
