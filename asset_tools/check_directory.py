"""Verify every indexed resource and reject damaged indices, without changing bodies."""
from pathlib import Path
import sys,json,struct
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'re_restore_work/tools'))
from restore import decode,sha
from directory_codec import parse,encode

def run(inputs,inventory):
 results=[]
 for source,relative in [('ngage_main','ngage/game/main.dz'),('ios','ios/main.dz'),('android','android/main.dz')]:
  e=next(e for e in inventory[source]['entries'] if e['path']=='common/environment.group.bin');b=decode((inputs/relative).read_bytes(),e);g=parse(b)
  assert encode(g)==b
  for cut in [0,5,30,38,g.storage_offset-1,len(b)-1]:
   try:parse(b[:cut])
   except ValueError:pass
   else:raise AssertionError('truncation accepted')
  first=next(r for r in g.records() if r.offset);bad=bytearray(b);bad[first.offset]^=1
  try:parse(bad)
  except ValueError:pass
  else:raise AssertionError('wrong indexed class accepted')
  results.append({'source':source,'sha256':sha(b),'entries':len(g.records()),'nonzero_offsets':sum(bool(r.offset) for r in g.records()),'zero_offset_entries_unresolved':sum(not r.offset for r in g.records()),'roundtrip':'byte-identical','truncation_and_header_mismatch_tests':'passed'})
 return results
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();results=run(a.inputs,json.loads(a.inventory.read_text()));a.report.write_text(json.dumps(results,indent=2)+'\n');print('Passed directory checks for all three archives')
