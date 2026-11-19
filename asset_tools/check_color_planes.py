"""Unpacked color-channel layout regression checks against explicit byte vectors."""
import argparse,json,struct
from pathlib import Path
from component_codec import Reader,Writer
from group_codec import iw_hash

def check(report):
 rgba=bytes([10,20,30,255,40,50,60,128,70,80,90,64]);plane=bytes([10,40,70,20,50,80,30,60,90,255,128,64])
 for mode in [0,2]:
  block={'class':iw_hash('CIwModelBlockCols'),'first':40,'count':3,'flags':0,'mode':mode,'colors':rgba};encoded=Writer('ngage').block(block);assert encoded[11:]==plane and encoded[11:]!=rgba;assert Reader(encoded,'ngage').block('CIwModelBlockCols')['colors']==rgba
 block={'class':iw_hash('CIwModelBlockCols'),'first':40,'count':3,'flags':0,'mode':1,'colors':bytes([10,10,10,255,40,40,40,255,70,70,70,255])};encoded=Writer('ngage').block(block);assert encoded[11:]==bytes([10,40,70]);assert Reader(encoded,'ngage').block('CIwModelBlockCols')['colors']==block['colors']
 report.write_text(json.dumps({'explicit_planar_vectors':'passed for modes 0 and 2','grayscale_byte_layout':'unchanged','native_control':'see native_flat_color_checks.json and captured control frames; arithmetic roundtrip alone is not sufficient'},indent=2)+'\n');print('Explicit channel-plane vectors and unchanged grayscale layout passed')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.report)
