from pathlib import Path
import sys,json,lzma,hashlib,base64,zlib,collections,time
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));from prepare_game import ngage_files,sha
ap=argparse.ArgumentParser(description="Build restoration copy/patch instructions from a verified prepared game directory.")
ap.add_argument('--ngage',type=Path,required=True);ap.add_argument('--ios-main',type=Path,required=True);ap.add_argument('--game-dir',type=Path,required=True)
ap.add_argument('--inventory',type=Path,default=Path(__file__).with_name('source_inventory.json'));ap.add_argument('--output',type=Path,default=Path(__file__).with_name('restoration_recipe.json.zlib'));args=ap.parse_args()
inv=json.loads(args.inventory.read_text());raw=ngage_files(args.ngage)
archives={'ngage':(args.game_dir/'main.dz').read_bytes(),'ios':args.ios_main.read_bytes()}
assert sha(archives['ngage'])==inv['ngage_main']['sha256'] and sha(archives['ios'])==inv['ios']['sha256']
entries={};aliases={}
for src,key in [('ngage','ngage_main'),('ios','ios')]:
 for e in inv[key]['entries']:
  if e['decompression']=='valid':
   key=src+'/'+e['path'];entries[key]={'archive':src,'offset':e['offset'],'size':e['decoded_bytes'],'sha256':e['decoded_sha256']}
   for x in e.get('embedded_lua',[]):aliases.setdefault(x['path'],set()).add(key)
recipe={'version':1,'ios_sha256':sha(archives['ios']),'ngage_main_sha256':sha(archives['ngage']),'sources':{},'files':{}}
for p in sorted(args.game_dir.rglob('*')):
 if not p.is_file():continue
 name=p.relative_to(args.game_dir).as_posix();target=p.read_bytes();h=sha(target);row={'sha256':h,'size':len(target)}
 if h in raw:row['raw']=h;recipe['files'][name]=row;continue
 path=name.removeprefix('overrides/');sources={}
 for key,e in entries.items():
  if key.split('/',1)[1]==path or key in aliases.get(path,set()):
   d=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE);b=d.decompress(archives[e['archive']][e['offset']:],max_length=e['size']+1);assert sha(b)==e['sha256'];sources[key]=b
 assert sources,(name,'missing donor source')
 # Exact source files need no patch data.
 equal=next((key for key,b in sources.items() if b==target),None)
 if equal:commands=[['c',equal,0,len(target)]]
 else:
  index={};minimum=12
  for key,b in sources.items():
   for i in range(len(b)-minimum+1):
    token=b[i:i+minimum];q=index.get(token)
    if q is None:index[token]=[(key,i)]
    elif len(q)<4:q.append((key,i))
  commands=[];literal=bytearray();i=0
  def flush():
   if literal:commands.append(['l',base64.b64encode(literal).decode()]);literal.clear()
  while i<len(target):
   best=0;choice=None
   for key,pos in index.get(target[i:i+minimum],()):
    b=sources[key];n=minimum;limit=min(len(b)-pos,len(target)-i)
    while n+64<=limit and b[pos+n:pos+n+64]==target[i+n:i+n+64]:n+=64
    while n<limit and b[pos+n]==target[i+n]:n+=1
    if n>best:best=n;choice=(key,pos)
   if choice:
    flush();commands.append(['c',choice[0],choice[1],best]);i+=best
   else:literal.append(target[i]);i+=1
  flush();del index
 row['commands']=commands
 for c in commands:
  if c[0]=='c':recipe['sources'][c[1]]=entries[c[1]]
 rebuilt=b''.join(sources[c[1]][c[2]:c[2]+c[3]]if c[0]=='c' else base64.b64decode(c[1]) for c in commands);assert rebuilt==target
 recipe['files'][name]=row
 print(name,len(target),len(commands),sum(len(base64.b64decode(c[1]))for c in commands if c[0]=='l'),flush=True)
p=args.output;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(zlib.compress(json.dumps(recipe,separators=(',',':')).encode(),9));print('Recipe bytes',p.stat().st_size,'files',len(recipe['files']),flush=True)
