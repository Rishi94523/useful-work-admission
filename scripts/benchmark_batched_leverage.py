"""Amendment 15: batched verification leverage on one CPU thread.

Per model and batch size B in {1, 8, 32, 128}: the server's cheapest native
batched inference (FP32 or INT8), batched verification from received bytes
(parse, hash, range checks, four projections per affine layer, nonlinear
operations), and a forced audit. Each timed repetition draws B distinct test
inputs; three warm-up repetitions are excluded and method order is randomised.
M1 checks (perturbation rejection and equality with the per-input verifier)
run on the first timed batch of every size. The GPU baseline is measured
separately by scripts/benchmark_gpu_central.py.
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
from research.inference.batched import BatchedVerifier
from research.inference.quantized_net import QuantizedNet, layers_from_sequential, layers_from_vgg
from research.inference.workloads import DATASET, INPUT_SHAPE, load_trained, load_vgg, mnist, cifar, verify_assets
from scripts.benchmark_inference_leverage import int8_model

OUT = ROOT / 'local-research/batched-leverage-2026-09-28'
PROTOCOL_COMMIT = 'fbe767f'
MODELS = ['mnist-mlp', 'mnist-cnn', 'cifar-cnn', 'mnist-wide-mlp', 'vgg11-bn']
BATCHES = [1, 8, 32, 128]
AUDIT = 0.08; WARMUP = 3; TIMED = 24
PHONES = json.loads((ROOT / 'local-research/device-inference-2026-09-28/summary.json').read_text(encoding='utf-8'))['phones']


def m1_checks(q, bv, images, trace, logits, rng):
    rejected = total = 0
    for layer in range(len(trace)):
        for offset in (1, -1, 2**31 - 1):
            forged = [t.copy() for t in trace]
            forged[layer][rng.integers(len(images)), rng.integers(forged[layer].shape[1])] += offset
            total += 1; rejected += not bv.verify(images, bv.pack(forged))[0]
    equal = True
    for i in range(min(8, len(images))):
        t, _ = q.trace(images[i]); ok, out = q.verify(images[i], t)
        equal &= ok and np.array_equal(out.ravel(), logits[i])
    return rejected, total, equal


def run(name, sets):
    data = sets[DATASET[name]]
    model = load_vgg() if name == 'vgg11-bn' else load_trained(name)
    layers = layers_from_vgg(model) if name == 'vgg11-bn' else layers_from_sequential(model)
    calib = data['train'][0][:256]
    q = QuantizedNet(model, layers, calib, INPUT_SHAPE[name]); q.prepare(); bv = BatchedVerifier(q); q.use_native()
    test_x = (data['cifar10_1'] if name == 'vgg11-bn' else data['test'])[0]
    int8 = int8_model(model, calib, INPUT_SHAPE[name]); fp32 = model
    rng = np.random.default_rng(20260928); rows = []
    per_input_trace = sum(int(np.prod(op.output_shape)) * 4 for op in q.ops)
    for batch in BATCHES:
        samples = []; m1 = None
        for rep in range(WARMUP + TIMED):
            idx = rng.choice(len(test_x), size=batch, replace=False); images = test_x[idx]
            trace, truth = bv.trace(images); blob = bv.pack(trace); batch_t = torch.from_numpy(images)
            calls = {'fp32': lambda: fp32(batch_t), 'int8': lambda: int8(batch_t),
                     'verify': lambda: bv.verify(images, blob), 'audit': lambda: bv.verify(images, blob, audit=True)}
            timing = {}
            with torch.inference_mode():
                for k in rng.permutation(list(calls)):
                    b = time.perf_counter_ns(); r = calls[k](); timing[k] = (time.perf_counter_ns() - b) / 1e6
                    if k in ('verify', 'audit'): assert r[0] and np.array_equal(r[1], truth), (name, batch, k)
            if rep == WARMUP: m1 = m1_checks(q, bv, images, trace, truth, rng)
            if rep >= WARMUP: samples.append(timing)
        med = {k: float(np.median([s[k] for s in samples])) for k in samples[0]}
        central = min(med['fp32'], med['int8']); v = med['verify']; a = med['audit']; veff = (1 - AUDIT) * v + AUDIT * a
        budget_s = batch * PHONES['Samsung M30s']['models'][name]['median_ms'] / 1000
        row = {'model': name, 'batch': batch, 'median_ms': med, 'central_ms': central,
               'central_backend': 'fp32' if med['fp32'] <= med['int8'] else 'int8',
               'verify_ms': v, 'audit_ms': a, 'verify_eff_ms': veff, 'verify_per_input_ms': veff / batch,
               'leverage_no_audit': central / v, 'leverage_8pct': central / veff,
               'trace_bytes': batch * per_input_trace, 'weight_bytes': q.weight_bytes(),
               'budget_phone_s': budget_s, 'budget_phone_within_patience': budget_s <= 10,
               'm1_rejected': m1[0], 'm1_total': m1[1], 'm1_equal_per_input': bool(m1[2]), 'samples': samples}
        rows.append(row)
        print('%-15s B=%-4d central %8.3f ms (%s) verify %8.3f audit %9.3f  Veff %8.3f  L0 %6.2f  L8 %6.2f  budget %5.1f s  M1 %d/%d %s'
              % (name, batch, central, row['central_backend'], v, a, veff, row['leverage_no_audit'], row['leverage_8pct'],
                 budget_s, m1[0], m1[1], m1[2]), flush=True)
    return rows


def main():
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    committed = subprocess.check_output(['git', 'show', PROTOCOL_COMMIT + ':docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') in (ROOT / 'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md').read_bytes().replace(b'\r\n', b'\n'), 'Protocol not committed'
    verify_assets(); OUT.mkdir(parents=True, exist_ok=True)
    files = ['scripts/benchmark_batched_leverage.py', 'scripts/benchmark_inference_leverage.py', 'research/inference/batched.py',
             'research/inference/quantized_net.py', 'research/inference/prepared_affine.py', 'research/inference/native_affine.py',
             'research/inference/workloads.py', 'tmp/native-verifier/affine_check.dll', 'data/inference-models/training.json']
    manifest = {'amendment': 15, 'protocol_commit': PROTOCOL_COMMIT, 'platform': platform.platform(), 'processor': platform.processor(),
                'python': sys.version, 'torch': torch.__version__, 'numpy': np.__version__, 'threads': 1, 'audit_rate': AUDIT,
                'batches': BATCHES, 'warmup': WARMUP, 'timed': TIMED,
                'files': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    sets = {'mnist': mnist(), 'cifar': cifar()}; rows = []
    for name in MODELS:
        rows += run(name, sets)
        (OUT / 'results.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
