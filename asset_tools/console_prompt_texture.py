"""Replace only the native OK button texture; preserve all other fixed resources."""
from pathlib import Path
import sys,struct,json
from PIL import Image
from group_codec import parse,encode,iw_hash
from restore import decode,sha

def apply(game,inventory):
 inv=json.loads(inventory.read_text());entry=next(e for e in inv['entries'] if e['path']=='common/fixed_wav.group.bin')
 raw=decode((game/'main.dz').read_bytes(),entry);g=parse(raw)
 r=next(r for r in g.resources() if r.class_id==iw_hash('CIwTexture') and r.in_group_hash==0x8fab1108)
 old=r.body;assert old[0]==20 and old[10]==22 and struct.unpack_from('<HH',old,13)==(32,32) and len(old)==568
 pal=struct.unpack('<16H',old[-33:-1]);colors=[((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,255 if v&0x8000 else 0) for v in pal]
 # Use the original texture's opaque/transparent palette and native dimensions.
 art=Path(__file__).resolve().parents[1]/'source/assets/bottomscreen'
 isolated=Image.open(art/'A_Only.png').convert('RGBA');assert isolated.size==(40,30)
 # Native lettering layer starts four pixels inside the 40-pixel button.
 # Preserve the supplied pixel art; only remove transparent canvas padding.
 im=Image.new('RGBA',(32,32));im.paste(isolated.crop((4,0,36,30)),(0,0))
 assert im.tobytes()==Image.open(art/'action_button_A.png').convert('RGBA').tobytes()
 idx=[min(range(16),key=lambda k:sum((p[t]-colors[k][t])**2 for t in range(4))) for p in im.getdata()]
 r.body=old[:23]+bytes(idx[i]|(idx[i+1]<<4) for i in range(0,len(idx),2))+old[-33:]
 out=encode(g);assert encode(parse(out))==out
 oldg=parse(raw);newg=parse(out)
 changed=[(a.class_id,a.in_group_hash) for a,b in zip(oldg.resources(),newg.resources()) if a.body!=b.body]
 assert changed==[(iw_hash('CIwTexture'),0x8fab1108)]
 p=game/'overrides/common/fixed_wav.group.bin';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(out)
 return {'changed_texture':'8fab1108','before':sha(raw),'after':sha(out),'non_target_resources_unchanged':True}
if __name__=='__main__':
 print(json.dumps(apply(Path(sys.argv[1]),Path(sys.argv[2])),indent=2))
