"""Check area projection against analytic lighting fields and coarse dark corners."""
from pathlib import Path
import struct,json
from group_codec import iw_hash
from lightmap_footprint import project

def check(report):
 verts=[(0,0,0),(2000,0,0),(2000,0,2000),(0,0,2000)]
 model={'blocks':[{'class':iw_hash('CIwModelBlockVerts'),'count':4,'unique':4,'data':struct.pack('<12h',*(p[k] for k in range(3) for p in verts))},{'class':iw_hash('CIwModelBlockGLTriList'),'count':6,'data':struct.pack('<6H',0,1,2,0,2,3)}]};uv=[(0,0),(4096,0),(4096,4096),(0,4096)]
 constant=lambda u,v:(37,77,123)
 assert all(max(abs(c[k]-constant(0,0)[k]) for k in range(3))<1e-6 for c in project(model,uv,constant).values())
 linear=lambda u,v:(20+180*u/4096,50+100*v/4096,80)
 result=project(model,uv,linear);assert max(abs(result[i][ch]-linear(*uv[i])[ch]) for i in range(4) for ch in range(3))<1e-6
 bilinear=lambda u,v:(20+100*u/4096+40*v/4096+50*u*v/(4096**2),)*3
 result=project(model,uv,bilinear);assert max(abs(result[i][ch]-bilinear(*uv[i])[ch]) for i in range(4) for ch in range(3))<1e-6
 interior=lambda u,v:(16*160*(u/4096)*(1-u/4096)*(v/4096)*(1-v/4096),)*3
 projected=project(model,uv,interior);assert all(interior(*p)==(0,0,0) for p in uv);values=[v[0] for v in projected.values()];assert min(values)>70 and max(values)-min(values)<1e-6
 dark=project(model,uv,lambda u,v:(3,3,3));assert all(abs(v[0]-3)<1e-6 for v in dark.values())
 small={'blocks':[dict(model['blocks'][0],data=struct.pack('<12h',*(int(p[k]/10) for k in range(3) for p in verts))),model['blocks'][1]]};assert project(small,uv,constant) is None
 result={'constant_linear_and_bilinear_fields':'exact within 1e-6','zero_corner_bright_interior_projected_values':values,'symmetric_quad_without_artificial_diagonal':'passed','genuinely_dark_surface_remains_dark':True,'small_props_excluded':True};report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);a=p.parse_args();check(a.report)
