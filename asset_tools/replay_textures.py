"""Replay original, unchanged iOS and converted-texture splash cases in isolation."""
from pathlib import Path
import argparse,json,os,re,shutil,subprocess
from audit_archives import inspect
from restore import decode,sha
from texture_probe import run

def main(inputs,probe,out):
 if out.exists():raise ValueError('choose a new output directory')
 out.mkdir(parents=True);fixtures={}
 for src,p in [('ngage_main',inputs/'ngage/game/main.dz'),('ios',inputs/'ios/main.dz')]:
  inv=inspect(p);entry=next(e for e in inv['entries'] if e['path']=='common/splash.group.bin')
  f=out/(src+'.group.bin');f.write_bytes(decode(p.read_bytes(),entry));fixtures[src]=f
 results=[]
 for case in ['original','unconverted_ios','converted_textures']:
  folder=out/case;game=folder/'game';shutil.copytree(inputs/'ngage/game',game)
  target=game/'overrides/common/splash.group.bin'
  if case=='unconverted_ios':target.parent.mkdir(parents=True);shutil.copy2(fixtures['ios'],target)
  if case=='converted_textures':run(fixtures['ngage_main'],fixtures['ios'],target)
  env=dict(os.environ,RE_HYBRID_RESOURCE='common/splash.group.bin',RE_HYBRID_TRACE=str((folder/'trace').resolve()))
  env.pop('RE_STREAM_TEST',None);env.pop('RE_STREAM_REFERENCE',None)
  with (folder/'runtime.log').open('w') as log:
   result=subprocess.run([str(probe.resolve()),str(game.resolve()),'180',str((folder/'frames').resolve()),str((folder/'user').resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60)
  log=(folder/'runtime.log').read_text(errors='replace');match=re.search(r'\[HybridResult\] result=(\d+) frames=(\d+) failed=(\d+)',log)
  row={'case':case,'exit_code':result.returncode,'summary':match.group(0) if match else None,
       'frames':int(match[2]) if match else None,'failed':int(match[3]) if match else None}
  results.append(row)
  if case=='unconverted_ios':assert result.returncode!=0 and row['frames']<180
  else:assert result.returncode==0 and row['frames']==180 and row['failed']==0
 report={'runtime_sha256':sha(probe.read_bytes()),'results':results,
  'limit':'splash texture conversion control only; original GUI/materials retained; no damaged scene repaired'}
 (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.inputs,a.probe,a.out)
