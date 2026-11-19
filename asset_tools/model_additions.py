"""Prepare only the missing static models, materials and opaque window texture."""
import struct,collections
from group_codec import iw_hash
from directory_codec import parse
from model_codec import read as glread,encode as glencode
from triangle_convert import convert,MODEL_IDS

def records(data):return {(r.class_id,r.name_hash):data[s:t-8 if t==len(data) else t] for r,s,t in parse(data).spans()}
def texture_convert(body,native_records):
 import texture2ddecoder
 from PIL import Image
 if body[0]!=0x14 or body[10]!=35 or body[-1]!=0:raise ValueError('new texture profile')
 w,h=struct.unpack_from('<HH',body,13);blob=body[23:-1]
 token,levels,bw,bh,size=struct.unpack_from('<5I',blob,8)
 if token!=0x8c02 or levels!=8 or (bw,bh,size)!=(w,h,w*h//2) or len(blob)!=72+sum(max(w>>i,8)*max(h>>i,8)//2 for i in range(levels)):raise ValueError('new texture PVRTC framing')
 templates=[b for (cl,_),b in native_records.items() if cl==iw_hash('CIwTexture') and len(b)>23 and b[0]==0x14 and b[10]==22 and struct.unpack_from('<H',b,13)[0]==w and struct.unpack_from('<H',b,17)[0]==w//2 and len(b)==23+w*struct.unpack_from('<H',b,15)[0]//2+33]
 if not templates:raise ValueError('no verified native texture template')
 rgba=texture2ddecoder.decode_pvrtc(blob[72:72+size],w,h,False)
 if any(v!=255 for v in rgba[3::4]):raise ValueError('new texture must be opaque')
 image=Image.frombytes('RGBA',(w,h),rgba,'raw','BGRA').convert('RGB');indexed=image.quantize(colors=16,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
 palette=indexed.getpalette()[:48];entries=[0x8000|(palette[i]>>3)|((palette[i+1]>>3)<<5)|((palette[i+2]>>3)<<10) for i in range(0,48,3)]
 indices=indexed.tobytes();packed=bytes(indices[i]|(indices[i+1]<<4) for i in range(0,len(indices),2))
 header=bytearray(templates[0][:23]);struct.pack_into('<H',header,15,h)
 return bytes(header)+packed+struct.pack('<16H',*entries)+b'\0'

def additions(native,donor,fixed):
 nr=records(native);dr=records(donor);available=set(nr)
 from group_codec import parse as group_parse
 available.update((r.class_id,r.in_group_hash) for r in group_parse(fixed).resources())
 result=[];report={'models':[],'materials':[],'texture':None,'native_fixed_group_dependencies':[]}
 mats={}
 for h in sorted(MODEL_IDS):
  body=dr[iw_hash('CIwModel'),h];m=glread(body);assert glencode(m)==body
  for mid in struct.unpack('<'+'I'*(len(m['materials'])//4),m['materials']):
   material=dr[iw_hash('CIwMaterial'),mid]
   if len(material)!=9 or material[0]!=1:raise ValueError('new material profile')
   flags=struct.unpack_from('<I',material,1)[0]
   if flags not in [0x50081,0x50080]:raise ValueError('new material flags')
   converted=material[:1]+struct.pack('<I',flags&~0x80)+material[5:];mats[mid]=converted
  flags=[struct.unpack_from('<I',mats[mid],1)[0] for mid in struct.unpack('<'+'I'*(len(m['materials'])//4),m['materials'])]
  output=convert(body,flags);result.append((iw_hash('CIwModel'),h,output));report['models'].append({'id':f'{h:08x}','triangles':sum(b['count']//3 for b in m['blocks'] if b['class']==iw_hash('CIwModelBlockGLTriList')),'baked_model_colors':any(b['class']==iw_hash('CIwModelBlockCols') for b in m['blocks']),'normals_omitted_with_baked_colors':any(b['class']==iw_hash('CIwModelBlockNorms') for b in m['blocks'])})
 for h,body in sorted(mats.items()):
  tex=struct.unpack_from('<I',body,5)[0];key=(iw_hash('CIwTexture'),tex)
  if key not in available:
   if tex!=0x43dd0f05:raise ValueError('unresolved new texture dependency')
   converted=texture_convert(dr[key],nr);result.append((*key,converted));available.add(key);report['texture']={'id':f'{tex:08x}','dimensions':[128,128],'profile':'opaque native 16-color ABGR1555; adaptive donor palette'}
  elif key not in nr:report['native_fixed_group_dependencies'].append(f'{tex:08x}')
  result.append((iw_hash('CIwMaterial'),h,body));report['materials'].append({'id':f'{h:08x}','texture':f'{tex:08x}','GPU_lightmap_flag_removed':True})
 report['native_fixed_group_dependencies']=sorted(set(report['native_fixed_group_dependencies']))
 # Order dependencies before models; index relocation keeps all original bodies.
 result.sort(key=lambda row:0 if row[0]==iw_hash('CIwTexture') else 1 if row[0]==iw_hash('CIwMaterial') else 2)
 return result,report
