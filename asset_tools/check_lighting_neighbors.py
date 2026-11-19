"""Verify neighbor rejection/weights and unchanged prior exact-match colors."""
import argparse,json,math
from pathlib import Path
from lighting_neighbors import neighbor_weights
from group_codec import parse,iw_hash
from component_codec import read
from color_contract import ColorContract

def check(previous,current,report):
 p=(0,0,0);surface=[(1,(0,0,1))]
 w,d=neighbor_weights(p,surface,[(1,0,0),(2,0,0),(0,0,1)],[[*surface],[*surface],[(2,(0,0,1))]],10)
 assert set(w)=={0,1} and abs(sum(w.values())-1)<1e-12 and w[0]>w[1]
 assert not neighbor_weights(p,surface,[(20,0,0)],[[*surface]],10)[0]
 assert not neighbor_weights(p,surface,[(1,0,0)],[[(1,(1,0,0))]],10)[0]
 assert not neighbor_weights(p,surface,[(0,0,5)],[[*surface]],10)[0]
 contract=ColorContract((current/'overrides/common/environment.group.bin').read_bytes());counts={'checked_arrays':0,'prior_baked_arrays_unchanged':0}
 def renders(e):
  for i,c in enumerate(e['components']):
   if 'entity' in c:
    for key,v in renders(c['entity']):yield (i,)+key,v
   if c.get('class')==iw_hash('CIwRenderableModelSpec') and 'colors' in c:yield (i,),c
 for path in ['levels/staffarea/staffarea.group.bin','levels/staffarea/staffarea_story.group.bin']:
  old={r.in_group_hash:r for r in parse((previous/'overrides'/path).read_bytes()).resources() if r.class_id==iw_hash('CIwEntSpec')}
  for r in parse((current/'overrides'/path).read_bytes()).resources():
   if r.class_id!=iw_hash('CIwEntSpec'):continue
   oldc=dict(renders(read(old[r.in_group_hash].body,'ngage')[0]))
   for key,c in renders(read(r.body,'ngage')[0]):
    colors=c['colors'];assert colors['count']>=contract.required[c['model']];counts['checked_arrays']+=1
    before=oldc[key]['colors']['colors']
    if before!=b'\xff'*len(before):
     assert colors['colors']==before;counts['prior_baked_arrays_unchanged']+=1
 assert counts=={'checked_arrays':448,'prior_baked_arrays_unchanged':420}
 result={'checks':counts,'synthetic_checks':['nearby same-surface inverse-distance weights','different material rejected','distant point rejected','perpendicular surface rejected','parallel displaced surface rejected']};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--previous',type=Path,required=True);p.add_argument('--current',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.previous,a.current,a.report)
