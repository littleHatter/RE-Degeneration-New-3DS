"""Prepare the supplied artwork as deterministic little-endian RGB565."""
from pathlib import Path
from PIL import Image
import struct
root=Path(__file__).resolve().parents[1]
art=root/'source/assets/bottomscreen'
out=root/'3ds/res_degene/ui/bottomscreen.bin'
names=['bottomscreenartwork','A','A2','B','B2','START','X1','X2']
sizes=[(320,240),(83,17),(83,17),(77,17),(77,17),(99,17),(61,17),(61,17)]
with out.open('wb') as f:
 f.write(struct.pack('<II',0x49554552,1))
 for name,size in zip(names,sizes):
  im=Image.open(art/(name+'.png')).convert('RGB');assert im.size==size
  for r,g,b in im.getdata():f.write(struct.pack('<H',((r>>3)<<11)|((g>>2)<<5)|(b>>3)))
print(out)

loading=Image.open(art/"loading.png").convert("RGB")
assert loading.size==(58,15)
with (out.parent/"loading.bin").open("wb") as f:
 f.write(struct.pack("<4I",0x444c4552,1,*loading.size))
 for r,g,b in loading.getdata():f.write(struct.pack("<H",((r>>3)<<11)|((g>>2)<<5)|(b>>3)))
