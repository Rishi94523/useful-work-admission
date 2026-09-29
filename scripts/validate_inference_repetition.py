"""Amendment 19: sequential, same-host full-pipeline CPU repetitions.

Keep historical GPU-inclusive measurements separate; include preparation and
audit-rate sensitivity. Run only while other campaigns are idle.
"""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import numpy as np
import torch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.inference.quantized_net import QuantizedNet,layers_from_sequential
from research.inference.native_dense import NativeDense
from research.inference.workloads import load_trained,mnist,verify_assets
from scripts.benchmark_inference_leverage import int8_model
from scripts.benchmark_native_dense import perturbations

OUT=ROOT/'local-research/inference-repetition-2026-09-29'


def main():
    OUT.mkdir(exist_ok=False);torch.set_num_threads(1);torch.set_num_interop_threads(1);verify_assets()
    manifest=dict(protocol_commit='a2d2af1',runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        native_sha256=hashlib.sha256((ROOT/'tmp/native-verifier/dense_check.dll').read_bytes()).hexdigest(),
        python=platform.python_version(),torch=torch.__version__,numpy=np.__version__,cpu=platform.processor(),
        scope='Same host, fastest measured CPU only; no GPU timings imported',sessions=3,warmups=12,timed=64,threads=1)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    data=mnist();calib=data['train'][0][:256];test_x=data['test'][0];rows=[]
    for session in range(3):
        for name in ('mnist-mlp','mnist-wide-mlp'):
            model=load_trained(name);b=time.perf_counter()
            q=QuantizedNet(model,layers_from_sequential(model),calib,(784,));q.prepare()
            prepare_ms=(time.perf_counter()-b)*1000;b=time.perf_counter();nd=NativeDense(q)
            fused_ms=(time.perf_counter()-b)*1000
            int8=int8_model(model,calib,(784,));q.use_native();rng=np.random.default_rng(20260929+session)
            for batch in (1,32):
                samples=[];checks=None
                for rep in range(12+64):
                    images=test_x[rng.choice(len(test_x),size=batch,replace=False)];blob=nd.forward(images)
                    reference=b''.join(q.pack(q.trace(i)[0]) for i in images[:4])
                    assert blob[:len(reference)]==reference
                    t=torch.from_numpy(images)
                    calls={'fp32':lambda:model(t),'int8':lambda:int8(t),'native':lambda:nd.forward(images),
                           'verify':lambda:nd.verify(images,blob),'audit':lambda:nd.verify(images,blob,audit=True)}
                    measured={}
                    with torch.inference_mode():
                        for k in rng.permutation(list(calls)):
                            b=time.perf_counter_ns();r=calls[k]();measured[k]=(time.perf_counter_ns()-b)/1e6
                            if k in ('verify','audit'):assert r[0]
                    if rep==12:checks=perturbations(nd,images,blob,rng)
                    if rep>=12:samples.append(measured)
                med={k:float(np.median([s[k] for s in samples])) for k in samples[0]}
                central=min(med[k] for k in ('fp32','int8','native'))
                sensitivity=[]
                for p in (0,.02,.08,.25,1):
                    v=(1-p)*med['verify']+p*med['audit']
                    sensitivity.append(dict(audit_rate=p,verification_ms=v,cpu_leverage=central/v,
                        amortized_leverage={str(n):central/(v+(prepare_ms+fused_ms)/n) for n in (100,1000,10000)}))
                rows.append(dict(session=session,model=name,batch=batch,median_ms=med,central_ms=central,
                    sketch_and_quantized_model_setup_ms=prepare_ms,fused_setup_ms=fused_ms,
                    perturbations_rejected=checks[0],perturbations_tested=checks[1],reference_exact=True,
                    sensitivity=sensitivity,samples=samples))
                (OUT/'results.json').write_text(json.dumps(rows,indent=2));print(name,batch,session,'L8',sensitivity[2]['cpu_leverage'],flush=True)
    ratios={}
    for name in ('mnist-mlp','mnist-wide-mlp'):
        for batch in (1,32):
            xs=[r['median_ms']['verify'] for r in rows if r['model']==name and r['batch']==batch]
            ratios[name+':'+str(batch)]=max(xs)/min(xs)
    summary=dict(IR1=all(r['perturbations_rejected']==r['perturbations_tested'] and r['reference_exact'] for r in rows),
        IR2=all(r<=1.25 for r in ratios.values()),session_max_min_verify=ratios,
        leverage_8pct={name+':'+str(b):[r['sensitivity'][2]['cpu_leverage'] for r in rows if r['model']==name and r['batch']==b]
                      for name in ('mnist-mlp','mnist-wide-mlp') for b in (1,32)})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
