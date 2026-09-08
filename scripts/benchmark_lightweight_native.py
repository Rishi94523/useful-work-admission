import hashlib,json,shutil,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.lightweight_docking import Assets
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07';a=Assets(BASE/'assets')
exe=BASE/'lightweight_kernel.exe';source=ROOT/'research/native/lightweight_kernel.cpp';flags=['-O3','-march=native','-std=c++17','-static-libgcc','-static-libstdc++']
subprocess.run([shutil.which('g++'),*flags,str(source),'-o',str(exe)],check=True)
results=[]
for l in [item for pair in zip(a.meta['ligands'][:8],a.meta['ligands'][16:24]) for item in pair]:
    bank=np.r_[a.meta['map_shape'],a.meta['origin_micro'],a.meta['spacing_micro'],a.meta['center_milli'],len(l['conformers_milli']),len(l['types']),len(a.rot),l['offset']%(len(l['conformers_milli'])*len(a.rot)*512),a.rot.ravel(),l['types'],np.array(l['conformers_milli']).ravel()].astype('<i4')
    bp=BASE/'native-bank.bin';bank.tofile(bp)
    for n in [32,4096]:
        output=BASE/'native-results.bin';r=json.loads(subprocess.check_output([str(exe),str(BASE/'assets/maps.bin'),str(bp),'8192',str(n),'7',str(output)],text=True))
        actual=np.fromfile(output,dtype='<i4').reshape(n,len(l['types']));expected=a.evaluate(l['id'],8192,n)
        if not np.array_equal(actual,expected):raise AssertionError('Native/Python integer disagreement')
        results.append({'id':l['id'],'poses':n,'heavy_atoms':l['heavy_atoms'],'integer_records_agree':True,**r})
(OUT/'native_kernel.json').write_text(json.dumps({'scope':'C++ optimized same integer objective, -march=native, one process at a time. Timings exclude file loading and output write, include per-atom record storage. First repetition cold; remaining six warm. Not a browser or proof benchmark.','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'compiler_flags':flags,'results':results},indent=2)+'\n')
print('Native integer control:',len(results),'cases agree')
