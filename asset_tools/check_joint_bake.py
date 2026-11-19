import numpy as np,json,argparse
from pathlib import Path
from staff_joint_bake import quadrature,solve,continuous_light
from check_scene_seams import run_case

def check(report):
 assert continuous_light(((30,60,120),b'\xff'*3),((35,63,119),b'\xff'*3))
 assert not continuous_light(((30,60,120),b'\xff'*3),((150,60,120),b'\xff'*3))
 assert not continuous_light(((30,60,120),b'\xff'*3),((30,60,120),b'\x80'*3))
 _,resources,seam,group,eligible=run_case(material=2)
 assert seam.apply([('fixture',group)],eligible,edge_filter=lambda nodes,instances:True)['matched_edge_pairs']==1
 _,resources,seam,group,eligible=run_case(rotation=1,material=2)
 assert seam.apply([('fixture',group)],eligible,edge_filter=lambda nodes,instances:True)['matched_edge_pairs']==0
 p=[(0,0,0),(2000,0,0),(2000,0,2000),(0,0,2000),(4000,0,0),(4000,0,2000)];uv=[(x*4096/4000,z*4096/2000) for x,y,z in p];faces=[(0,1,2,3),(1,4,5,2)]
 h=np.zeros((6,6));rhs=np.zeros((6,3))
 light=lambda u,v:np.array([20+160*u/4096,30+100*v/4096,180-70*u/4096])
 areas=[]
 for ids in faces:
  area_sum=0
  for basis,t,area in quadrature(p,uv,ids,24):
   area_sum+=area
   for a,wa in zip(ids,basis):
    rhs[a]+=area*wa*light(*t)
    for b,wb in zip(ids,basis):h[a,b]+=area*wa*wb
  areas.append(area_sum)
 assert max(abs(x-4000000) for x in areas)<1e-6
 result,_=solve(h,rhs,np.ones((6,3))*100)
 expected=np.array([light(*t) for t in uv]);linear_error=float(np.max(abs(result-expected)));assert linear_error<.001
 # Area-weighted compromise for one shared variable with unequal areas.
 result,_=solve(np.array([[5.]]),np.array([[20.+4*100,40.+4*20,200.+4*10]]),np.ones((1,3))*100)
 assert np.max(abs(result[0]-np.array([84,24,48])))<.001
 # A bright interior with dark corner samples must remain visibly lit.
 h=np.zeros((4,4));rhs=np.zeros((4,3));ids=(0,1,2,3)
 for basis,t,area in quadrature(p,uv,ids,32):
  x=t[0]/2048;y=t[1]/4096;target=np.array([160,80,40])*16*x*(1-x)*y*(1-y)
  for a,wa in zip(ids,basis):
   rhs[a]+=area*wa*target
   for b,wb in zip(ids,basis):h[a,b]+=area*wa*wb
 result,_=solve(h,rhs,np.ones((4,3))*50)
 assert result[:,0].min()>70 and np.ptp(result[:,0])<.01
 assert np.max(abs(result[:,0]-2*result[:,1]))<.01 and np.max(abs(result[:,0]-4*result[:,2]))<.01
 r={'two_connected_panels_RGB_linear_field_max_error':linear_error,'quadrature_preserves_physical_area':True,'unequal_area_weighting':True,'shared_edge_uses_single_variable':True,'coloured_bright_interior_preserved':True,'RGB_ratios_preserved':True,'cross_material_joins_allowed_when_light_continuous':True,'source_colour_discontinuities_and_intrinsic_tints_preserved':True,'sharp_crease_still_excluded':True,'dark_corner_fixture_red_values':result[:,0].tolist()};report.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--report',type=Path,required=True);check(p.parse_args().report)
