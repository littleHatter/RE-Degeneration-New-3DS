"""Diagnostic only: compare native gray, planar RGB, and the old incorrect layout.
Copies a previously built Plane Cargo diagnostic game; never edits that input tree.
"""
from pathlib import Path
import argparse,json,struct,shutil,os,subprocess,re
from group_codec import parse,encode,iw_hash
from directory_codec import parse as index_read
from component_codec import read,encode as entity_encode

def run(game,probe,out,input_path,encoding,rgb_ids):
 if out.exists():raise ValueError('choose a fresh output directory')
 copied=out/'game';shutil.copytree(game,copied);environment=copied/'overrides/common/environment.group.bin';data=bytearray(environment.read_bytes());found=False
 for r,s,t in index_read(data).spans():
  if r.class_id==iw_hash('CIwTexture') and r.name_hash==0xf8d4ea66:
   if t-s!=2104 or data[s+10]!=22:raise ValueError('unverified Cargo panel texture profile')
   data[t-33:t-1]=b'\xff'*32;found=True
 if not found:raise ValueError('Cargo panel texture absent')
 environment.write_bytes(data);labels=[]
 def visit(e,name,trail=()):
  for k,c in enumerate(e['components']):
   if 'entity' in c:visit(c['entity'],name,trail+(k,))
   if c.get('class')!=iw_hash('CIwRenderableModelSpec') or 'colors' not in c:continue
   i=len(labels);color=tuple(32+32*((i//(7**ch))%7) for ch in range(3)) if rgb_ids and encoding!='gray' else (i+20,)*3
   if max(color)>255:raise ValueError('too many diagnostic instances')
   labels.append({'index':i,'entity':name,'component':trail+(k,),'model':f'{c["model"]:08x}','intended_rgb':color});b=c['colors'];b['mode']=1 if encoding=='gray' else 2;raw=bytes(color+(255,))*b['count']
   # Invert the correct writer's channel transpose to reproduce old bad bytes.
   b['colors']=bytes(raw[ch*b['count']+j] for j in range(b['count']) for ch in range(4)) if encoding=='legacy' else raw
 for suffix in ['', '_story']:
  path=copied/f'overrides/levels/planecargo/planecargo{suffix}.group.bin';g=parse(path.read_bytes())
  for r in g.resources():
   if r.class_id==iw_hash('CIwEntSpec'):
    e,_=read(r.body,'ngage');visit(e,f'{r.in_group_hash:08x}');r.body=entity_encode(e,'ngage')
  path.write_bytes(encode(g))
 (out/'labels.json').write_text(json.dumps(labels,indent=2)+'\n');env=dict(os.environ,RE_TEST_ROUTE='staffarea',RE_HYBRID_BUNDLE='staffarea',RE_HYBRID_RESOURCE='common/environment.group.bin')
 for k in ['RE_AUDIO_CAPTURE','RE_HYBRID_TRACE','RE_STREAM_TEST','RE_STREAM_REFERENCE']:env.pop(k,None)
 with (out/'runtime.log').open('w') as log:r=subprocess.run([str(probe.resolve()),str(copied.resolve()),'900',str((out/'frames').resolve()),str((out/'user').resolve()),str(input_path.resolve())],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
 summaries=re.findall(r'\[HybridResult\].*',(out/'runtime.log').read_text());result={'encoding':encoding,'rgb_identifiers':rgb_ids,'instances':len(labels),'runtime_exit':r.returncode,'summary':summaries,'diagnostic_only':True};(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
 if r.returncode or '[HybridResult] result=0 frames=900 failed=0' not in summaries:raise RuntimeError('control did not complete')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game',type=Path,required=True);p.add_argument('--probe',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--encoding',choices=['gray','planar','legacy'],required=True);p.add_argument('--rgb-identifiers',action='store_true');a=p.parse_args();run(a.game,a.probe,a.out,a.input,a.encoding,a.rgb_identifiers)
