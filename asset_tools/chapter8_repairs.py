from pathlib import Path
import json,struct,copy,argparse
from group_codec import parse,encode,iw_hash
from restore import decode

def apply(checkpoint,game,report):
 inv=json.loads((checkpoint/'reports/inventory.json').read_text());path='levels/vipplane/vipplane_story.group.bin';cl=iw_hash('CVideoPhoneDialogue');name=iw_hash('mission8_hunnigan1_onboardplane');entry=next(e for e in inv['ios']['entries'] if e['path']==path);donor=parse(decode((checkpoint/'inputs/ios/main.dz').read_bytes(),entry));g=parse((game/'overrides'/path).read_bytes());native={r.in_group_hash:r for r in g.resources() if r.class_id==cl};source={r.in_group_hash:r for r in donor.resources() if r.class_id==cl};assert native[0x682ecfc4].body==source[0x682ecfc4].body
 body=source[name].body;n=struct.unpack_from('<I',body)[0];assert n==6 and len(body)==4+n*5
 main=(game/'main.dz').read_bytes();hash_entry=next(e for e in inv['ngage_main']['entries'] if e['path']=='localisation/localisehashes.dat');hashes=decode(main,hash_entry)
 text_ids=[struct.unpack_from('<I',body,4+i*5)[0] for i in range(n)];assert all(struct.pack('<I',h) in hashes for h in text_ids)
 if name not in native:
  target=next(c for s in g.sections if s.classes for c in s.classes if c.class_id==cl);target.resources.append(copy.deepcopy(source[name]));(game/'overrides'/path).write_bytes(encode(g))
 else:assert native[name].body==body
 localisations=[]
 for lang in ['english','french','german','italian','spanish']:
  path='localisation/'+lang+'.dat';e=next(e for e in inv['ngage_main']['entries'] if e['path']==path);b=decode(main,e);old=b'2008 C/RECGFP';assert b.count(old)==1;new=b'2008 CAPCOM'.ljust(len(old),b' ');fixed=b.replace(old,new);assert len(fixed)==len(b)
  p=game/'overrides'/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(fixed);localisations.append(path)
 report.write_text(json.dumps({'VIP_conversation_added':f'{name:08x}','native_donor_control_body_identical':True,'dialogue_lines':n,'all_line_ids_exist_in_native_localisation':True,'copyright_replacements':localisations,'localisation_lengths_offsets_unchanged':True},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser()
 for k in ['checkpoint','game','report']:p.add_argument('--'+k,type=Path,required=True)
 apply(**vars(p.parse_args()))
