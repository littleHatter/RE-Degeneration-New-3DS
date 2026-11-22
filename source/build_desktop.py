"""Build the debuggable Linux/Unicorn target incrementally (Python + g++ + zlib)."""
import pathlib,subprocess,sys
import unicorn
root=pathlib.Path(__file__).resolve().parent
package=pathlib.Path(unicorn.__file__).resolve().parent
if not sys.platform.startswith('linux'):raise SystemExit('This build recipe is currently verified on Linux only.')
source=['main_probe.cpp','gles.cpp','hw_host.cpp','loader.cpp','heap.cpp','runtime_s3e.cpp','cpu_unicorn.cpp','cpu_native.cpp','third_party/lzma/LzmaDec.c']
flags=['-std=c++17','-DMGS_GLES','-Ithird_party/gles1','-O2','-g','-fno-omit-frame-pointer','-I'+str(package/'include')]
build=root/'.desktop-build';build.mkdir(exist_ok=True)
headers=list(root.rglob('*.h'))+[pathlib.Path(__file__)]
header_time=max(p.stat().st_mtime for p in headers)
objects=[]
for name in source:
    src=root/name;obj=build/(src.stem+'.o');objects.append(obj)
    if not obj.exists() or obj.stat().st_mtime<max(src.stat().st_mtime,header_time):
        subprocess.run(['g++']+flags+['-c',str(src),'-o',str(obj)],cwd=root,check=True)
exe=root/'re_hybrid_probe'
if not exe.exists() or exe.stat().st_mtime<max(p.stat().st_mtime for p in objects):
    subprocess.run(['g++']+list(map(str,objects))+['-L'+str(package/'lib'),'-Wl,-rpath,'+str(package/'lib'),'-l:libunicorn.so.2','-ldl','-lz','-l:libEGL.so.1','-l:libGL.so.1','-o',str(exe)],cwd=root,check=True)
print('Built',exe)
