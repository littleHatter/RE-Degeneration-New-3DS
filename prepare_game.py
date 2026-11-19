#!/usr/bin/env python3
"""Prepare the verified Resident Evil New 3DS baseline from user-supplied data.
Python 3.10+, standard library only. No downloads; no game data is embedded here.
"""
import argparse,base64,hashlib,json,lzma,struct,tempfile,zipfile,zlib
from pathlib import Path,PurePosixPath

def sha(b):return hashlib.sha256(b).hexdigest()
def fields(b,typed=True,et=None):
 o=0
 while o<len(b):
  if len(b)-o<(8 if typed else 4):return
  if typed:t=struct.unpack_from('<I',b,o)[0];o+=4
  else:t=et
  n=struct.unpack_from('<I',b,o)[0];o+=4
  if n&0x80000000:
   if o+4>len(b):raise ValueError('truncated package field')
   n=(n&0x7fffffff)|(struct.unpack_from('<I',b,o)[0]<<31);o+=4
  if n>len(b)-o:raise ValueError('package field exceeds input')
  yield t,b[o:o+n];o+=(n+3)&~3

def array(b):
 if len(b)<4:raise ValueError('truncated package array')
 return list(fields(b[4:],False,struct.unpack_from('<I',b)[0]))
def decompress(b):
 if len(b)<12:raise ValueError('truncated compressed package field')
 alg,n=struct.unpack_from('<IQ',b)
 if alg not in (0,1) or n>256*1024*1024:raise ValueError('unsupported package compression')
 r=zlib.decompress(b[12:]) if alg==1 else b[12:]
 if len(r)!=n:raise ValueError('package size mismatch')
 return r

def collect(b):
 out=[]
 for t,v in fields(b):
  if t==24:out.append(v)
  elif t in (13,26,27,28):out+=collect(v)
  elif t==2:
   for et,e in array(v):
    if et==24:out.append(e)
    elif et in (26,27,28):out+=collect(e)
 return out

def ngage_files(path):
 if path.is_dir():
  out=[]
  for p in path.rglob('*'):
   if p.is_file() and p.suffix.lower() in ('.xe3u','.s3e','.dz','.ngdat','.jpg'):out.append(p.read_bytes())
 else:
  p=path.read_bytes();mark=p.find(b'Content-ID: <Game>')
  if mark<0:raise ValueError('N-Gage game payload not found')
  start=p.find(b'\r\n\r\n',mark)
  if start<0:raise ValueError('N-Gage payload header is incomplete')
  sis=p[start+4:]
  if len(sis)<16 or struct.unpack_from('<I',sis)[0]!=0x10201a7a:raise ValueError('unsupported game package layout')
  contents=next(fields(sis[16:]))[1];parts=dict(fields(contents));ctrl=decompress(parts[3]);fds=[]
  for _,unit in array(next(fields(parts[30]))[1]):
   for t,v in fields(unit):
    if t==2:fds+=array(v)
  out=[]
  for d in collect(ctrl):
   idx=struct.unpack_from('<I',d,len(d)-4)[0]
   if idx>=len(fds):raise ValueError('invalid package file index')
   out.append(decompress(next(fields(fds[idx][1]))[1]))
 # The executable is stored as a separate compressed payload in the package.
 for b in list(out):
  if b[:4]!=b'XE3U':
   try:
    d=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE);x=d.decompress(b,max_length=8*1024*1024)
    if d.eof and x[:4]==b'XE3U':out.append(x)
   except lzma.LZMAError:pass
 return {sha(b):b for b in out}

def donor_archive(path,expected,label="iOS"):
 if not path.is_dir() and path.suffix.lower()==".rar":
  raise ValueError("Extract the BREW RAR first, then pass its ResidentEvil/main.dz using --brew.")
 if path.is_dir():candidates=list(path.rglob('main.dz'))
 else:candidates=[path]
 for p in candidates:
  if zipfile.is_zipfile(p):
   with zipfile.ZipFile(p) as z:
    for n in z.infolist():
     if n.filename.lower().endswith('/main.dz') or n.filename.lower()=='main.dz':
      b=z.read(n)
      if sha(b)==expected:return b
  else:
   b=p.read_bytes()
   if sha(b)==expected:return b
 raise ValueError(label+' donor does not match the supported baseline version')

def reconstruct(ngage,ios,brew,recipe):
 raw=ngage_files(ngage);archives={'ios':donor_archive(ios,recipe['ios_sha256']),'brew':donor_archive(brew,recipe['brew_sha256'],'BREW')}
 native=recipe['ngage_main_sha256']
 if native not in raw:raise ValueError('N-Gage main archive does not match the supported baseline version')
 archives['ngage']=raw[native];cache={}
 def source(name):
  if name not in cache:
   e=recipe['sources'][name];d=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
   b=d.decompress(archives[e['archive']][e['offset']:],max_length=e['size']+1)
   if not d.eof or len(b)!=e['size'] or sha(b)!=e['sha256']:raise ValueError('resource integrity check failed: '+name)
   cache[name]=b
  return cache[name]
 result={}
 for name,e in recipe['files'].items():
  p=PurePosixPath(name)
  if p.is_absolute() or '..' in p.parts or '\\' in name:raise ValueError('unsafe output path')
  if 'raw' in e:
   if e['raw'] not in raw:raise ValueError('required N-Gage payload was not found: '+name)
   b=raw[e['raw']]
  else:
   out=bytearray()
   for command in e['commands']:
    if command[0]=='c':
     _,key,offset,size=command;s=source(key)
     if offset<0 or size<0 or offset+size>len(s):raise ValueError('invalid restoration copy')
     out.extend(s[offset:offset+size])
    elif command[0]=='l':out.extend(base64.b64decode(command[1],validate=True))
    else:raise ValueError('unsupported restoration command')
   b=bytes(out)
  if len(b)!=e['size'] or sha(b)!=e['sha256']:raise ValueError('prepared file hash mismatch: '+name)
  result[name]=b
 return result

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--ngage',required=True,type=Path,help='N-Gage package or extracted game directory');ap.add_argument('--ios',required=True,type=Path,help='matching iOS IPA, extracted app directory, or main.dz');ap.add_argument('--brew',required=True,type=Path,help='extracted verified BREW main.dz, directory, or ZIP');ap.add_argument('--output',type=Path,default=Path(__file__).resolve().parent/'3ds/res_degene/game');ap.add_argument('--verify-only',action='store_true');a=ap.parse_args()
 recipe=json.loads(zlib.decompress((Path(__file__).resolve().parent/'preparation/restoration_recipe.json.zlib').read_bytes()))
 try:
  files=reconstruct(a.ngage,a.ios,a.brew,recipe)
  if not a.verify_only:
   a.output.parent.mkdir(parents=True,exist_ok=True)
   # Validate all inputs and outputs before replacing any files. Saves live outside game/.
   with tempfile.TemporaryDirectory(prefix='res_prepare_',dir=a.output.parent)as tmp:
    staging=Path(tmp)
    for name,b in files.items():p=staging/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    for name in files:
     p=a.output/name;p.parent.mkdir(parents=True,exist_ok=True);(staging/name).replace(p)
  print(('Verified' if a.verify_only else 'Prepared')+f' {len(files)} game files; all baseline hashes match.')
  if not a.verify_only:print('Game folder: '+str(a.output.resolve()))
 except (OSError,ValueError,KeyError,struct.error,lzma.LZMAError,zipfile.BadZipFile)as e:ap.exit(1,'Preparation failed: '+str(e)+'\n')
if __name__=='__main__':main()
