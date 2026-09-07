"""Link a map-export/oracle helper against the previously built pinned Vina."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1];OLD=ROOT/'tmp/docking-pilot';NEW=ROOT/'tmp/docking-ladder'
NEW.mkdir(exist_ok=True)
compiler=shutil.which('g++')
if not compiler:raise RuntimeError('Run native docking build with a UCRT MinGW compiler first')
meta=json.loads((ROOT/'docs/evaluation/docking_pilot_2026-09-06/native_build.json').read_text())
flags=['-O3','-std=c++17','-DNDEBUG','-DBOOST_ALL_NO_LIB','-D_WIN32_WINNT=0x0A00','-DBOOST_USE_WINAPI_VERSION=0x0A00','-I'+str(OLD/'cached-source'),'-I'+str(OLD/'boost/ucrt64/include')]
source=ROOT/'research/native/docking_grid_export.cpp';obj=NEW/'docking_grid_export.o';exe=NEW/'docking_grid_export.exe'
subprocess.run([compiler,*flags,'-c',str(source),'-o',str(obj)],check=True)
objects=[p for p in (OLD/'build').glob('*.o') if p.stem!='docking_worker']
libs=[str(OLD/'boost/ucrt64/lib'/Path(p).name) for p in meta['libraries']]
subprocess.run([compiler,*map(str,objects),str(obj),*libs,'-static-libgcc','-static-libstdc++','-lws2_32','-lbcrypt','-o',str(exe)],check=True)
(ROOT/'docs/evaluation/docking_ladder_2026-09-07/grid_build.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'upstream_build':'../docking_pilot_2026-09-06/native_build.json','flags':flags,'scope':'Pinned Vina map export and independent grid-scoring oracle, no search/proof changes.'},indent=2)+'\n')
print('Built trusted map-export helper')
