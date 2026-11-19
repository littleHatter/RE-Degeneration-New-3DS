"""Reproduce Staff door interactions using normal inputs and a one-shot entry route."""
from pathlib import Path
import argparse,json,os,re,subprocess
from staff_pipeline import build
from lua_test_route import staff_route_once,load,encode
from restore import decode,sha

def run(inputs,audit,probe,out,frames,input_path=None):
 if out.exists():raise ValueError('choose a fresh output directory')
 game=out/'game';manifest=build(inputs,audit,game,True)
 inv=json.loads((audit/'inventory.json').read_text());entry=next(e for e in inv['ngage_main']['entries'] if e['path']=='levels/vip/vip.luc');original=decode((inputs/'ngage/game/main.dz').read_bytes(),entry);routed=staff_route_once(original)
 assert encode(load(routed)['children'][16]['children'][0])==encode(load(original)['children'][16])
 (game/'overrides/levels/vip/vip.luc').write_bytes(routed)
 for row in manifest['files']:
  if row['path']=='levels/vip/vip.luc':row.update(sha256=sha(routed),bytes=len(routed),category='one-shot test route with original handler retained')
 manifest['test_route']='first VIP BEGIN_ROOM enters Staff; later events use original VIP handler';(game/'staff_bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
 lines=input_path.read_text() if input_path else ''.join(f'{f} {f+3} 208\n' for f in range(200,800,60))+'1000 1002 76\n1050 1200 204\n1230 1290 207\n1320 1440 204\n1450 1453 208\n1800 1920 207\n1920 1980 204\n2010 2013 208\n'
 script=out/'input.txt';script.write_text(lines);env=dict(os.environ,RE_TEST_ROUTE='staffarea',RE_HYBRID_BUNDLE='staffarea',RE_HYBRID_RESOURCE='common/environment.group.bin',RE_AUDIO_CAPTURE=str((out/'audio.wav').resolve()))
 for key in ['RE_STREAM_TEST','RE_STREAM_REFERENCE','RE_HYBRID_TRACE']:env.pop(key,None)
 with (out/'runtime.log').open('w') as log:result=subprocess.run([str(probe.resolve()),str(game.resolve()),str(frames),str((out/'frames').resolve()),str((out/'user').resolve()),str(script.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 text=(out/'runtime.log').read_text(errors='replace');opened=re.findall(r'\[S3E\] Open (levels/[^\n]+)',text);scripts=[p for p in opened if p.endswith('.luc')];sequence=[]
 for p in scripts:
  if not sequence or sequence[-1]!=p:sequence.append(p)
 m=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',text)
 report={'runtime_exit':result.returncode,'summary':m.group(0) if m else None,'level_script_sequence':sequence,'staff_then_vip_resources':any(sequence[i:i+2]==['levels/staffarea/staffarea.luc','levels/vip/vip.luc'] for i in range(len(sequence)-1)),'staff_vip_staff_resources':any(sequence[i:i+3]==['levels/staffarea/staffarea.luc','levels/vip/vip.luc','levels/staffarea/staffarea.luc'] for i in range(len(sequence)-2)),'level_opens':opened,'runtime_sha256':sha(probe.read_bytes()),'input_sha256':sha(script.read_bytes()),'one_shot_route_sha256':sha(routed),'original_VIP_handler_retained_byte_exact':True,'visual_confirmation_required':True,'full_game_restored':False}
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
 if result.returncode or not m or m.groups()!=('0',str(frames),'0'):raise RuntimeError('bounded interaction run failed; inspect report')
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--audit',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--frames',type=int,default=2600);p.add_argument('--input',type=Path);a=p.parse_args();run(a.inputs,a.audit,a.probe,a.out,a.frames,a.input)
