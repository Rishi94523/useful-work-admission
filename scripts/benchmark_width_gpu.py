"""Amendment 21 GPU baseline: the synthetic width-sweep networks on the GPU,
FP32 and FP16, B = 1, timed end to end (host-to-device copy, forward pass,
device-to-host copy, synchronised). Runs in the CUDA environment tmp/gpu-models.
"""
import copy
import json
from pathlib import Path
import sys
import time
import numpy as np
import torch
from torch import nn
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'local-research/width-sweep-2026-09-29'
WIDTHS = [512, 1024, 2048, 4096, 8192]
WARM, TIMED = 20, 64


def main():
    assert torch.cuda.is_available(), 'CUDA required'
    rows = []
    for n in WIDTHS:
        torch.manual_seed(20260929 + n)   # same construction as benchmark_width_sweep.synthetic
        base = nn.Sequential(nn.Linear(n, n), nn.ReLU(), nn.Linear(n, 10)).eval().cuda()
        models = {'fp32': (base, torch.float32), 'fp16': (copy.deepcopy(base).half(), torch.float16)}
        inputs = np.random.default_rng(20260929 + n).standard_normal((WARM + TIMED, n)).astype(np.float32)
        med = {}
        with torch.inference_mode():
            for kind, (model, dtype) in models.items():
                times = []
                for i, x in enumerate(inputs):
                    host = torch.from_numpy(x[None]); torch.cuda.synchronize(); b = time.perf_counter_ns()
                    model(host.to('cuda').to(dtype)).float().cpu(); torch.cuda.synchronize()
                    if i >= WARM: times.append((time.perf_counter_ns() - b) / 1e6)
                med[kind] = float(np.median(times))
        rows.append({'width': n, 'median_ms': med, 'gpu_central_ms': min(med.values()), 'gpu_backend': min(med, key=med.get)})
        print('n=%-5d fp32 %.3f fp16 %.3f' % (n, med['fp32'], med['fp16']), flush=True)
    meta = {'device': torch.cuda.get_device_name(0), 'torch': torch.__version__, 'cuda': torch.version.cuda, 'python': sys.version}
    (OUT / 'gpu.json').write_text(json.dumps({'meta': meta, 'rows': rows}, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
