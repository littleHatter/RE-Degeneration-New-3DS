"""Optional shared-edge pass for a converted scene bundle; inputs stay intact."""
from pathlib import Path
import argparse,json
from group_codec import parse,encode
from shared_edge_lighting import SeamPass
from restore import sha

def smooth(game,scene,report):
 if scene not in ['planecargo','staffarea','warehouse','planecrashed','generatortunnels','infirmary','planeexit','dutyfreewest','dutyfreeeast','vipplane','security','planeentrance']:raise ValueError('unvalidated scene')
 manifest=json.loads((game/'staff_bundle.json').read_text());paths=[f'levels/{scene}/{scene}{suffix}.group.bin' for suffix in ['', '_story']];intact={r['path'] for r in manifest['files'] if r['category'].startswith('intact original')}
 groups=[(path,parse((game/'overrides'/path).read_bytes())) for path in paths if (game/'overrides'/path).exists() and path not in intact]
 eligible={(r['scene'],r['entity'],r['model']) for r in manifest['lightmap_bake']['instances'] if 'output_colors' in r}
 floors={}
 if scene=='warehouse':
  floors={(r['entity'],tuple(r['component']),r['color_index']):r['minimum_rgb'] for r in manifest.get('warehouse_visibility',{}).get('minimum_constraints',[])}
 result=SeamPass((game/'overrides/common/environment.group.bin').read_bytes(),game/'resident_evil.xe3u').apply(groups,eligible,floors);result['scene']=scene
 for path,g in groups:
  payload=encode(g);assert encode(parse(payload))==payload;(game/'overrides'/path).write_bytes(payload)
  row=next(r for r in manifest['files'] if r['path']==path);row.update(sha256=sha(payload),bytes=len(payload),category='converted scene with optional shared-edge lighting')
 manifest.setdefault('shared_edge_lighting',{})[scene]=result;(game/'staff_bundle.json').write_text(json.dumps(manifest,indent=2)+'\n');report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='edits'},indent=2));return result
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--game',type=Path,required=True);p.add_argument('--scene',required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args();smooth(a.game,a.scene,a.report)
