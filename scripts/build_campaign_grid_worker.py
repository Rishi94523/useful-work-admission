"""Link a campaign helper against the already pinned Vina objects."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'tmp/docking-pilot';BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'
compiler=shutil.which('g++');source=ROOT/'research/native/campaign_grid_worker.cpp';obj=BASE/'campaign_grid_worker.o';exe=BASE/'campaign_grid_worker.exe'
flags=['-O3','-std=c++17','-DNDEBUG','-DBOOST_ALL_NO_LIB','-D_WIN32_WINNT=0x0A00','-DBOOST_USE_WINAPI_VERSION=0x0A00','-I'+str(OLD/'cached-source'),'-I'+str(OLD/'boost/ucrt64/include')]
subprocess.run([compiler,*flags,'-c',str(source),'-o',str(obj)],check=True)
meta=json.loads((ROOT/'docs/evaluation/docking_pilot_2026-09-06/native_build.json').read_text());libs=[str(OLD/'boost/ucrt64/lib'/Path(p).name) for p in meta['libraries']]
objects=[p for p in (OLD/'build').glob('*.o') if p.stem!='docking_worker']
subprocess.run([compiler,*map(str,objects),str(obj),*libs,'-static-libgcc','-static-libstdc++','-lws2_32','-lbcrypt','-o',str(exe)],check=True)
(OUT/'native_build.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'upstream':'../docking_pilot_2026-09-06/native_build.json','flags':flags,'scope':'Vina 1.2.7 no_refine maps, native oracle and moderate-search baseline; local trusted process only.'},indent=2)+'\n')
print('Campaign native worker built')
