"""Amendment 21: verification leverage against layer width, one CPU thread.

Synthetic n -> n -> 10 networks (ReLU), quantized and prepared exactly as the
classifiers, verified by the amendment-15b native kernel. Per width, B = 1,
twelve warm-ups and 64 timed distinct inputs, randomised method order:
PyTorch FP32 and INT8, native exact forward, native verification, native
verification with audit. The GPU baseline is scripts/benchmark_width_gpu.py.
"""
import os
for var in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'): os.environ[var] = '1'
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
import torch
from torch import nn
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from research.inference.native_dense import NativeDense
from research.inference.quantized_net import QuantizedNet, layers_from_sequential
from scripts.benchmark_inference_leverage import int8_model

OUT = ROOT / 'local-research/width-sweep-2026-09-29'
PROTOCOL_COMMIT = '8e77235'
WIDTHS = [512, 1024, 2048, 4096, 8192]
WARM, TIMED, AUDIT = 12, 64, 0.08


def synthetic(n):
    """Same construction in the CPU and GPU scripts: seeded default init."""
    torch.manual_seed(20260929 + n)
    model = nn.Sequential(nn.Linear(n, n), nn.ReLU(), nn.Linear(n, 10)).eval()
    rng = np.random.default_rng(20260929 + n)
    calib = rng.standard_normal((256, n)).astype(np.float32)
    inputs = rng.standard_normal((WARM + TIMED, n)).astype(np.float32)
    return model, calib, inputs


def run(n):
    model, calib, inputs = synthetic(n)
    t0 = time.perf_counter()
    q = QuantizedNet(model, layers_from_sequential(model), calib, (n,)); q.prepare(); nd = NativeDense(q); q.use_native()
    prepare_ms = (time.perf_counter() - t0) * 1000
    int8 = int8_model(model, calib, (n,))
    # W1: exactness against the reference path and sampled perturbations.
    equal = True
    for x in inputs[:4]:
        blob = nd.forward(x[None]); tr, _ = q.trace(x)
        equal &= blob == q.pack(tr)
        ok, logits = nd.verify(x[None], blob); ref_ok, ref = q.verify(x, tr)
        equal &= ok and ref_ok and np.array_equal(ref.ravel(), logits[0])
    trace = np.frombuffer(nd.forward(inputs[:1]), dtype='<i4'); rng = np.random.default_rng(n); rejected = total = offset = 0
    for width in nd.dims[1:]:
        for delta in (1, -1, 2**31 - 1):
            forged = trace.astype(np.int64); forged[offset + rng.integers(width)] += delta
            total += 1; rejected += not nd.verify(inputs[:1], forged.astype('<i4').tobytes())[0]
        offset += int(width)
    order = np.random.default_rng(20260929); samples = []
    with torch.inference_mode():
        for i, x in enumerate(inputs):
            batch = x[None]; blob = nd.forward(batch); t = torch.from_numpy(batch)
            calls = {'fp32': lambda: model(t), 'int8': lambda: int8(t), 'native_forward': lambda: nd.forward(batch),
                     'verify': lambda: nd.verify(batch, blob), 'audit': lambda: nd.verify(batch, blob, audit=True)}
            timing = {}
            for k in order.permutation(list(calls)):
                b = time.perf_counter_ns(); r = calls[k](); timing[k] = (time.perf_counter_ns() - b) / 1e6
                if k in ('verify', 'audit'): assert r[0]
            if i >= WARM: samples.append(timing)
    med = {k: float(np.median([s[k] for s in samples])) for k in samples[0]}
    cpu = min(med['fp32'], med['int8'], med['native_forward'])
    veff = (1 - AUDIT) * med['verify'] + AUDIT * med['audit']
    row = {'width': n, 'macs': n * n + 10 * n, 'weight_bytes': q.weight_bytes(), 'trace_bytes': nd.width * 4, 'prepare_ms': prepare_ms,
           'median_ms': med, 'central_cpu_ms': cpu, 'central_cpu_backend': min(('fp32', 'int8', 'native_forward'), key=lambda k: med[k]),
           'verify_ms': med['verify'], 'audit_ms': med['audit'], 'verify_eff_ms': veff,
           'leverage_cpu_no_audit': cpu / med['verify'], 'leverage_cpu_8pct': cpu / veff,
           'w1_equal': bool(equal), 'w1_rejected': rejected, 'w1_total': total, 'samples': samples}
    print('n=%-5d fp32 %.3f int8 %.3f native %.3f | verify %.4f audit %.3f | L0 %.2f L8 %.2f | weights %.1f MB | W1 %s %d/%d' % (
        n, med['fp32'], med['int8'], med['native_forward'], med['verify'], med['audit'], row['leverage_cpu_no_audit'], row['leverage_cpu_8pct'],
        row['weight_bytes'] / 1e6, equal, rejected, total), flush=True)
    return row


def main():
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    committed = subprocess.check_output(['git', 'show', PROTOCOL_COMMIT + ':docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') in (ROOT / 'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md').read_bytes().replace(b'\r\n', b'\n'), 'Protocol not committed'
    OUT.mkdir(parents=True, exist_ok=True)
    files = ['scripts/benchmark_width_sweep.py', 'research/inference/native_dense.py', 'research/inference/native/dense_check.c',
             'tmp/native-verifier/dense_check.dll', 'research/inference/quantized_net.py', 'research/inference/prepared_affine.py']
    (OUT / 'manifest.json').write_text(json.dumps({'amendment': 21, 'protocol_commit': PROTOCOL_COMMIT, 'platform': platform.platform(),
        'processor': platform.processor(), 'python': sys.version, 'torch': torch.__version__, 'numpy': np.__version__, 'threads': 1,
        'widths': WIDTHS, 'warmup': WARM, 'timed': TIMED, 'audit_rate': AUDIT,
        'files': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}, indent=2), encoding='utf-8')
    rows = []
    for n in WIDTHS:
        rows.append(run(n)); (OUT / 'results.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
