"""Amendment 15b: native fused verification of dense networks, one CPU thread.

Per model and batch size: PyTorch FP32 and INT8 inference, the native exact
forward pass, native verification (hash, parse, projections, requantisation)
and native verification with the exact audit. B = 1 uses 128 distinct inputs
after 12 warm-up runs; B = 32 uses 24 batches after 3 warm-up batches. Method
order is randomised. The GPU baseline is amendment 15's measurement.
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
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from research.inference.native_dense import NativeDense
from research.inference.quantized_net import QuantizedNet, layers_from_sequential
from research.inference.workloads import load_trained, mnist, verify_assets
from scripts.benchmark_inference_leverage import int8_model

OUT = ROOT / 'local-research/native-dense-2026-09-28'
PROTOCOL_COMMIT = 'a1c1d83'
MODELS = ['mnist-mlp', 'mnist-wide-mlp']
PLAN = {1: (12, 128), 32: (3, 24)}   # batch -> (warm-up, timed)
AUDIT = 0.08
GPU = {(r['model'], r['batch']): r['gpu_central_ms'] for r in json.loads(
    (ROOT / 'local-research/batched-leverage-2026-09-28/gpu_central.json').read_text(encoding='utf-8'))['rows']}


def perturbations(nd, images, blob, rng):
    trace = np.frombuffer(blob, dtype='<i4'); rejected = total = offset = 0
    for width in nd.dims[1:]:
        for delta in (1, -1, 2**31 - 1):
            forged = trace.astype(np.int64); forged[rng.integers(len(images)) * nd.width + offset + rng.integers(width)] += delta
            forged = forged.astype('<i4').tobytes(); total += 1; rejected += not nd.verify(images, forged)[0]
        offset += int(width)
    return rejected, total


def run(name, data):
    model = load_trained(name); calib = data['train'][0][:256]
    q = QuantizedNet(model, layers_from_sequential(model), calib, (784,)); q.prepare(); nd = NativeDense(q); q.use_native()
    test_x = data['test'][0]; int8 = int8_model(model, calib, (784,)); rng = np.random.default_rng(20260928); rows = []
    for batch, (warm, timed) in PLAN.items():
        samples = []; n1 = None
        for rep in range(warm + timed):
            images = test_x[rng.choice(len(test_x), size=batch, replace=False)]
            blob = nd.forward(images); t = torch.from_numpy(images)
            reference = b''.join(q.pack(q.trace(i)[0]) for i in images[:4])
            assert blob[:len(reference)] == reference, 'native trace differs from reference'
            calls = {'fp32': lambda: model(t), 'int8': lambda: int8(t), 'native_forward': lambda: nd.forward(images),
                     'verify': lambda: nd.verify(images, blob), 'audit': lambda: nd.verify(images, blob, audit=True)}
            timing = {}
            with torch.inference_mode():
                for k in rng.permutation(list(calls)):
                    b = time.perf_counter_ns(); r = calls[k](); timing[k] = (time.perf_counter_ns() - b) / 1e6
                    if k in ('verify', 'audit'): assert r[0]
            if rep == warm:
                ok, logits = nd.verify(images, blob)
                equal = all(np.array_equal(q.verify(images[i], q.trace(images[i])[0])[1].ravel(), logits[i]) for i in range(min(8, batch)))
                n1 = (*perturbations(nd, images, blob, rng), bool(ok and equal))
            if rep >= warm: samples.append(timing)
        med = {k: float(np.median([s[k] for s in samples])) for k in samples[0]}
        candidates = {'fp32': med['fp32'], 'int8': med['int8'], 'native_forward': med['native_forward'], 'gpu': GPU[(name, batch)]}
        best = min(candidates, key=candidates.get); central = candidates[best]
        v = med['verify']; a = med['audit']; veff = (1 - AUDIT) * v + AUDIT * a
        row = {'model': name, 'batch': batch, 'median_ms': med, 'gpu_central_ms': GPU[(name, batch)], 'central_ms': central, 'central_backend': best,
               'verify_ms': v, 'audit_ms': a, 'verify_eff_ms': veff, 'leverage_no_audit': central / v, 'leverage_8pct': central / veff,
               'n1_rejected': n1[0], 'n1_total': n1[1], 'n1_equal': n1[2], 'weight_bytes': q.weight_bytes(), 'trace_bytes': batch * nd.width * 4,
               'samples': samples}
        rows.append(row)
        print('%-15s B=%-3d fp32 %.4f int8 %.4f native %.4f gpu %.4f -> central %.4f (%s) | verify %.4f audit %.4f Veff %.4f | L0 %.2f L8 %.2f | N1 %d/%d %s'
              % (name, batch, med['fp32'], med['int8'], med['native_forward'], GPU[(name, batch)], central, best, v, a, veff,
                 row['leverage_no_audit'], row['leverage_8pct'], n1[0], n1[1], n1[2]), flush=True)
    return rows


def main():
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    committed = subprocess.check_output(['git', 'show', PROTOCOL_COMMIT + ':docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') in (ROOT / 'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md').read_bytes().replace(b'\r\n', b'\n'), 'Protocol not committed'
    verify_assets(); OUT.mkdir(parents=True, exist_ok=True)
    files = ['scripts/benchmark_native_dense.py', 'research/inference/native_dense.py', 'research/inference/native/dense_check.c',
             'tmp/native-verifier/dense_check.dll', 'research/inference/quantized_net.py', 'research/inference/prepared_affine.py',
             'research/inference/workloads.py', 'data/inference-models/training.json']
    manifest = {'amendment': '15b', 'protocol_commit': PROTOCOL_COMMIT, 'platform': platform.platform(), 'processor': platform.processor(),
                'python': sys.version, 'torch': torch.__version__, 'numpy': np.__version__, 'threads': 1, 'audit_rate': AUDIT,
                'compiler': subprocess.check_output(['gcc', '--version'], text=True).split('\n')[0],
                'cflags': '-std=c11 -O3 -march=native -Wall -Wextra -Werror -shared', 'plan': PLAN,
                'files': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    data = mnist(); rows = []
    for name in MODELS: rows += run(name, data)
    (OUT / 'results.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
