"""Restore two missing Staff mesh material definitions without changing existing resources.
Run with the game directory from Test 6. No save or executable changes.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'asset_tools'))
from group_codec import iw_hash
from model_additions import records
from staff_pipeline import append_resources
from software_model_codec import read
PAIRS={0xa157664f:0x26a22c1f,0xa1576655:0x4c565c65}
def repair(game):
 p=game/'overrides/common/environment.group.bin';original=p.read_bytes();r=records(original);cl=iw_hash('CIwMaterial');template=r[cl,0xf5aecebe]
 # Both donor materials are byte-identical to the already converted control material.
 assert template==bytes.fromhex('0101000200ae2b8522')
 assert (iw_hash('CIwTexture'),0x22852bae) in r
 additions=[]
 for model,material in PAIRS.items():
  assert read(r[iw_hash('CIwModel'),model])['materials']==struct.pack('<I',material)
  if (cl,material) in r:assert r[cl,material]==template
  else:additions.append((cl,material,template))
 result=append_resources(original,additions) if additions else original;updated=records(result)
 for key,body in r.items():assert updated[key]==body
 assert len(updated)==len(r)+len(additions)
 p.write_bytes(result)
 return {'added_materials':[f'{h:08x}' for _,h,_ in additions],'all_existing_resource_bodies_unchanged':True,'existing_texture_reused':'22852bae','before_sha256':hashlib.sha256(original).hexdigest(),'after_sha256':hashlib.sha256(result).hexdigest()}
if __name__=='__main__':
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('game',type=Path);args=a.parse_args();print(json.dumps(repair(args.game),indent=2))
