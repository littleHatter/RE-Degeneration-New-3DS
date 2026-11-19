"""Controlled splash texture conversion using an intact N-Gage target profile.
Not a converter for damaged scene groups: all non-texture records stay original.
PVRTC decoder: texture2ddecoder 1.0.6 (MIT). No guessed texture variants accepted.
"""
from pathlib import Path
import argparse,copy,json,struct
from group_codec import parse,encode,iw_hash
from restore import sha

def dims(b):
 if len(b)<23 or b[0]!=0x14 or b[-1]!=0:raise ValueError('unsupported texture profile')
 return struct.unpack_from('<HH',b,13)
def convert(donor,target):
 w,h=dims(target)
 if dims(donor)!=(w,h) or target[10]!=22 or len(target)!=23+w*h//2+32+1:
  raise ValueError('unsupported target profile')
 if donor[10]==17:
  if len(donor)!=23+w*h//2+48+1:raise ValueError('unexpected indexed texture length')
  p=donor[-49:-1];pal=struct.pack('<16H',*[0x8000|(p[j+2]>>3)|((p[j+1]>>3)<<5)|((p[j]>>3)<<10) for j in range(0,48,3)])
  return target[:23]+donor[23:-49]+pal+b'\0','indexed BGR888 palette to ABGR1555'
 if donor[10]!=35:raise ValueError('unsupported donor texture encoding')
 blob=donor[23:-1]
 if len(blob)<72:raise ValueError('short native texture wrapper')
 declared=struct.unpack_from('<I',donor,19)[0]
 token,levels,bw,bh,size=struct.unpack_from('<5I',blob,8)
 if (token,levels,bw,bh,size)!=(0x8c02,1,w,h,max(w,8)*max(h,8)//2) or len(blob)!=72+size or declared!=len(blob):
  raise ValueError('unsupported PVRTC wrapper')
 if w&(w-1) or h&(h-1) or w<8 or h<8 or w*h>1048576:raise ValueError('unsupported PVRTC dimensions')
 import texture2ddecoder
 bgra=texture2ddecoder.decode_pvrtc(blob[72:],w,h,False)
 if len(bgra)!=w*h*4:raise ValueError('bad decoded texture size')
 palette=struct.unpack('<16H',target[-33:-1]);colors=[((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,255 if v&32768 else 0) for v in palette]
 indices=[]
 for j in range(0,len(bgra),4):
  b,g,r,a=bgra[j:j+4];pixel=(r,g,b,a)
  indices.append(min(range(16),key=lambda k:sum((pixel[t]-colors[k][t])**2 for t in range(4))))
 packed=bytes(indices[j]|indices[j+1]<<4 for j in range(0,len(indices),2))
 return target[:23]+packed+target[-33:],'PVRTC4 RGBA decoded and quantized to reference N-Gage palette'

def run(original,donor,out):
 ng=parse(original.read_bytes());ios=parse(donor.read_bytes());result=copy.deepcopy(ng);texture=iw_hash('CIwTexture');donors={r.in_group_hash:r for r in ios.resources() if r.class_id==texture};rows=[]
 for r in result.resources():
  if r.class_id!=texture:continue
  old=r.body;r.body,method=convert(donors[r.in_group_hash].body,old)
  rows.append({'id':f'{r.in_group_hash:08x}','method':method,'matches_original_bytes':r.body==old,'sha256':sha(r.body)})
 b=encode(result)
 if encode(parse(b))!=b:raise ValueError('converted group round trip failed')
 out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b)
 report={'scope':'textures only; all original N-Gage GUI and material records retained','original_sha256':sha(original.read_bytes()),'donor_sha256':sha(donor.read_bytes()),'output_sha256':sha(b),'textures':rows}
 out.with_suffix(out.suffix+'.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('donor',type=Path);p.add_argument('output',type=Path);a=p.parse_args();run(a.original,a.donor,a.output)
