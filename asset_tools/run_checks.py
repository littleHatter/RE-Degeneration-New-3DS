"""Replay the bounded desktop cases; invoke from the checkpoint root."""
from pathlib import Path
import argparse,os,subprocess,json
p=argparse.ArgumentParser();p.add_argument('--work',type=Path,default=Path('replay'));args=p.parse_args();root=Path(__file__).resolve().parents[1];work=args.work.resolve();exe=root/'source/re_hybrid_probe'
if not exe.exists():raise SystemExit('Build source/re_hybrid_probe first.')
checks=[('original','original','common/splash.group.bin',180,True),('identical','identical','common/splash.group.bin',180,True),('ios','ios','common/splash.group.bin',180,False),('story_original','original','common/scripts/storymissions.luc',1200,False),('story_android','android_script','common/scripts/storymissions.luc',1200,False)]
results=[]
for name,case,target,frames,stream in checks:
 out=work/'runs'/name;out.mkdir(parents=True,exist_ok=True);env=os.environ.copy();env['RE_HYBRID_RESOURCE']=target;env['RE_HYBRID_TRACE']=str(out/'trace')
 for key in ['RE_STREAM_TEST','RE_STREAM_REFERENCE','PAN_FILE_TRACE','PAN_INSTRUCTION_LIMIT']:env.pop(key,None)
 if stream:env['RE_STREAM_TEST']='1';env['RE_STREAM_REFERENCE']=str(work/'fixtures/ngage_main/common/splash.group.bin')
 command=[str(exe),str(work/'cases'/case),str(frames),str(out/'frames'),str(out/'user')]
 if name.startswith('story_'):command.append(str(root/'tools/story_input.txt'))
 with (out/'run.log').open('wb') as log:
  try:result=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60).returncode
  except subprocess.TimeoutExpired:result=124
 results.append({'case':name,'exit_code':result,'requested_frames':frames});print(name,'exit',result,flush=True)
(work/'run_results.json').write_text(json.dumps(results,indent=2)+'\n')
