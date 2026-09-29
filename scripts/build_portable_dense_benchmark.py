"""Export a PII-free Windows benchmark, with no Python package dependencies."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.inference.quantized_net import QuantizedNet,layers_from_sequential
from research.inference.native_dense import NativeDense
from research.inference.workloads import load_trained,mnist,verify_assets


def main():
    torch.set_num_threads(1);torch.set_num_interop_threads(1);verify_assets()
    out=ROOT/'tmp/ryzen-verification-benchmark';out.mkdir(exist_ok=False)
    source=ROOT/'research/inference/native/dense_check.c'
    shutil.copy2(source,out/'dense_check.c');shutil.copy2(ROOT/'scripts/portable_dense_benchmark.py',out/'benchmark.py')
    flags=['-std=c11','-O3','-march=x86-64','-Wall','-Wextra','-Werror','-shared','-static-libgcc']
    subprocess.run(['gcc',*flags,str(source),'-o',str(out/'dense_check.dll')],check=True)
    data=mnist();models=[]
    for name in ('mnist-mlp','mnist-wide-mlp'):
        model=load_trained(name);begin=time.perf_counter()
        q=QuantizedNet(model,layers_from_sequential(model),data['train'][0][:256],(784,));q.prepare()
        nd=NativeDense(q);prep_ms=(time.perf_counter()-begin)*1000;folder=out/name;folder.mkdir()
        for k in ('w','bias','s','r','rb','bounds','mult'):(folder/(k+'.bin')).write_bytes(getattr(nd,k).tobytes())
        images=data['test'][0][1:129];(folder/'inputs.bin').write_bytes(nd.inputs(images).tobytes())
        hashes=[hashlib.sha256(nd.forward(images[i:i+1])).hexdigest() for i in range(128)]
        models.append(dict(name=name,dims=nd.dims.tolist(),trace_hashes=hashes,export_host_preparation_ms=prep_ms))
    (out/'RUN_BENCHMARK.cmd').write_text('@echo off\ncd /d "%~dp0"\necho Plug in AC power. Close heavy apps. Turn off battery saver.\nwhere py >nul 2>nul\nif errorlevel 1 (python -B benchmark.py) else (py -3 -B benchmark.py)\npause\n')
    (out/'README.txt').write_text('Ryzen verification benchmark (amendment 19b)\n\nExtract this ZIP completely into a folder, plug in AC power, close heavy apps and turn off battery saver. Double-click RUN_BENCHMARK.cmd. Python must be 64-bit Windows Python 3.9 or newer. No pip installs, Codex, administrator rights or Internet are needed.\n\nReturn result.json after it finishes. If Python is not found or a DLL error appears, return the error text. Do not bypass antivirus protection. The package contains our compiled C verifier; its complete source is dense_check.c. All payloads are checksum-verified before the DLL loads.\n\nCollected: CPU model, OS/Python versions, logical CPU count, AC/battery status, timings and correctness. No hostname, username, account, IP, or personal files are collected. No data is uploaded automatically.\n\nThis compares portable exact-native kernels, not PyTorch/GPU or full browser latency. Prepared projections are public test fixtures, not production secret keys.\n')
    manifest=dict(protocol_commit='83ac5f0',models=models,cflags=flags,
        limitations='Portable exact-integer kernel comparison. Quantized inputs and prepared projections supplied; no sketch-generation/input-quantization costs in verification. Native forward emits full trace, not optimized logits only. Not fastest CPU/GPU central inference.',
        files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(out).as_posix())
    print('Package',archive,'bytes',archive.stat().st_size,'SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__=='__main__':main()
