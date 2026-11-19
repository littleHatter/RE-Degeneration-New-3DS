"""Match the supplied unpressed buttons exactly to the full layout; encode RGB565."""
from pathlib import Path
import argparse,struct,json
from PIL import Image
import numpy as np
NAMES=['1','2','3','4','5','6','7','8','9','asterisk','0','hash']
def build(assets,out,report):
 base=np.asarray(Image.open(assets/'keypadscreencomplete.png').convert('RGB'));assert base.shape==(240,320,3);buttons=[];states=[[],[]]
 def rgb565(a):
  a=a.astype(np.uint16);return (((a[:,:,0]>>3)<<11)|((a[:,:,1]>>2)<<5)|(a[:,:,2]>>3)).astype('<u2').tobytes()
 for i,name in enumerate(NAMES):
  u=np.asarray(Image.open(assets/'unpressed'/f'{name}.png').convert('RGB'));p=np.asarray(Image.open(assets/'pressed'/f'{name}.png').convert('RGB'));assert u.shape==p.shape==(40,80,3)
  candidates=[]
  for y in range(201):
   for x in range(241):
    if np.array_equal(base[y:y+40,x:x+80],u):candidates.append((x,y))
  assert len(candidates)==1,(name,candidates);x,y=candidates[0];key=77 if name=='asterisk' else 76 if name=='hash' else 13+int(name);buttons.append((x,y,80,40,key,i));states[0].append(rgb565(u));states[1].append(rgb565(p))
 data=struct.pack('<6I',0x504b4552,1,320,240,12,0)+b''.join(struct.pack('<6H',*b) for b in buttons)+rgb565(base)+b''.join(states[0])+b''.join(states[1]);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);report.write_text(json.dumps({'buttons':[dict(name=name,x=b[0],y=b[1],width=b[2],height=b[3],key=b[4]) for name,b in zip(NAMES,buttons)],'bytes':len(data),'format':'RGB565, row-major, both states'},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--assets',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--report',type=Path,required=True);build(**vars(p.parse_args()))
