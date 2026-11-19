"""Verify the private checkpoint inputs and create isolated replay cases."""
from pathlib import Path
import argparse,hashlib,json,lzma,shutil
from audit_archives import inspect
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,default=Path('replay'));args=p.parse_args()
root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'provenance.json').read_text())
for name,info in manifest['checkpoint_inputs'].items():
 data=(root/'inputs'/name).read_bytes()
 if hashlib.sha256(data).hexdigest()!=info['sha256']:raise SystemExit('Input differs from the audited checkpoint: '+name)
if args.work.exists():raise SystemExit('Choose a new empty --work directory.')
work=args.work;work.mkdir(parents=True)
archives={k:root/'inputs'/path for k,path in {'ngage_main':'ngage/game/main.dz','ngage_protected':'ngage/game/bin/protected.dz.ngdat','ios':'ios/main.dz','android':'android/main.dz'}.items()}
reports={k:inspect(path) for k,path in archives.items()};(work/'inventory.json').write_text(json.dumps(reports,indent=2)+'\n')
def decode(key,entry):
 raw=archives[key].read_bytes();out=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE).decompress(raw[entry['offset']:]);assert hashlib.sha256(out).hexdigest()==entry['decoded_sha256'];return out
for key in ['ngage_main','ios']:
 entry=next(e for e in reports[key]['entries'] if e['path']=='common/splash.group.bin');out=work/'fixtures'/key/entry['path'];out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(decode(key,entry))
script='common/scripts/storymissions.luc';original=next(e for e in reports['ngage_main']['entries'] if e['path']==script);ngage_script=decode('ngage_main',original);donor=None
for entry in reports['android']['entries']:
 for lua in entry.get('embedded_lua',[]):
  if lua['path']==script:
   raw=decode('android',entry);donor=raw[lua['offset']:lua['offset']+lua['bytes']]
assert donor==ngage_script
for key,data in [('ngage_main',ngage_script),('android',donor)]:
 out=work/'fixtures'/key/script;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data)
for case in ['original','identical','ios','android_script']:
 out=work/'cases'/case;shutil.copytree(root/'inputs/ngage/game',out)
 if case!='original':
  path=script if case=='android_script' else 'common/splash.group.bin';key={'identical':'ngage_main','ios':'ios','android_script':'android'}[case];target=out/'overrides'/path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(work/'fixtures'/key/path,target)
print('Prepared four isolated cases; source archives are unchanged.')
