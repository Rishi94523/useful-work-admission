"""Amendment 14: verification time, leverage and delivery bytes per model.

One native thread; 128 distinct test inputs per model, 12 warm-up iterations
excluded, method order randomised per input. The server's central baseline is
the cheaper of FP32 and native INT8 inference. Verification is full-trace
checking from received bytes (parse, hash, range checks, four projections per
affine layer, verifier-side nonlinear operations). The audit is verification
plus exact recomputation of every affine layer.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from research.inference.quantized_net import QuantizedNet, layers_from_sequential, layers_from_vgg
from research.inference.workloads import DATASET, INPUT_SHAPE, load_trained, load_vgg, mnist, cifar, verify_assets

OUT = ROOT / 'local-research/inference-leverage-2026-09-28'
PROTOCOL_COMMIT = '5105313'
MODELS = ['mnist-mlp', 'mnist-cnn', 'cifar-cnn', 'vgg11-bn', 'mnist-wide-mlp']
AUDIT = 0.08


def int8_model(model, calib, shape):
    from torch.ao.quantization import get_default_qconfig_mapping
    from torch.ao.quantization.quantize_fx import prepare_fx, convert_fx
    torch.backends.quantized.engine = 'x86' if 'x86' in torch.backends.quantized.supported_engines else 'onednn'
    example = (torch.from_numpy(calib[:1]),)
    prepared = prepare_fx(copy.deepcopy(model), get_default_qconfig_mapping('x86'), example)
    with torch.inference_mode():
        for s in range(0, 256, 32): prepared(torch.from_numpy(calib[s:s + 32]))
        return convert_fx(prepared)


def run(name, sets):
    data = sets[DATASET[name]]
    model = load_vgg() if name == 'vgg11-bn' else load_trained(name)
    layers = layers_from_vgg(model) if name == 'vgg11-bn' else layers_from_sequential(model)
    calib = data['train'][0][:256]
    q = QuantizedNet(model, layers, calib, INPUT_SHAPE[name]); q.prepare(); q.use_native()
    test_x, test_y = data['cifar10_1'] if name == 'vgg11-bn' else data['test']
    # L1: every single-entry perturbation of every layer is rejected.
    trace, logits = q.trace(test_x[0]); assert q.verify(test_x[0], trace, audit=True)[0]
    attacks = 0
    for i in range(len(trace)):
        for offset in (1, -1, 2**31 - 1):
            forged = [t.copy() for t in trace]; forged[i].flat[0] += offset
            assert not q.verify(test_x[0], forged)[0], (name, i, offset); attacks += 1
    accuracy = float(np.mean(q.batch_predictions(test_x) == test_y))
    int8 = int8_model(model, calib, INPUT_SHAPE[name]); fp32 = model
    rng = np.random.default_rng(20260928); ids = list(range(1, 129)); samples = []
    with torch.inference_mode():
        for it, i in enumerate([1] * 12 + ids):
            image = test_x[i]; tr, truth = q.trace(image); blob = q.pack(tr)
            calls = {'fp32': lambda: fp32(torch.from_numpy(image[None])),
                     'int8': lambda: int8(torch.from_numpy(image[None])),
                     'verify': lambda: q.verify(image, q.unpack(blob)),
                     'audit': lambda: q.verify(image, q.unpack(blob), audit=True)}
            timing = {}
            for k in rng.permutation(list(calls)):
                b = time.perf_counter_ns(); r = calls[k](); timing[k] = (time.perf_counter_ns() - b) / 1e6
                if k in ('verify', 'audit'): assert r[0] and np.array_equal(r[1], truth)
            if it >= 12: samples.append(timing)
    med = {k: float(np.median([s[k] for s in samples])) for k in samples[0]}
    central = min(med['fp32'], med['int8']); v = med['verify']; a = med['audit']; veff = (1 - AUDIT) * v + AUDIT * a
    return {'model': name, 'dataset': DATASET[name], 'test_inputs': len(test_y), 'quantized_accuracy': accuracy,
            'operators': [{'name': o.name, 'conv': o.conv, 'input_shape': list(o.input_shape), 'output_shape': list(o.output_shape), 'macs': o.macs} for o in q.ops],
            'macs': sum(o.macs for o in q.ops), 'perturbations_rejected': attacks,
            'median_ms': med, 'central_ms': central, 'central_backend': 'fp32' if med['fp32'] <= med['int8'] else 'int8',
            'verify_ms': v, 'audit_ms': a, 'verify_eff_ms': veff,
            'leverage_no_audit': central / v, 'leverage_8pct': central / veff,
            'trace_bytes': len(q.pack(trace)), 'weight_bytes': q.weight_bytes(), 'samples': samples}


def main():
    torch.set_num_threads(1); torch.set_num_interop_threads(1)
    committed = subprocess.check_output(['git', 'show', PROTOCOL_COMMIT + ':docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') in (ROOT / 'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md').read_bytes().replace(b'\r\n', b'\n'), 'Protocol not committed'
    verify_assets(); OUT.mkdir(parents=True, exist_ok=True)
    files = ['scripts/benchmark_inference_leverage.py', 'research/inference/quantized_net.py', 'research/inference/prepared_affine.py',
             'research/inference/native_affine.py', 'research/inference/native/affine_check.c', 'research/inference/workloads.py',
             'tmp/native-verifier/affine_check.dll', 'data/inference-models/training.json']
    manifest = {'amendment': 14, 'protocol_commit': PROTOCOL_COMMIT, 'platform': platform.platform(), 'processor': platform.processor(),
                'python': sys.version, 'torch': torch.__version__, 'numpy': np.__version__, 'threads': 1, 'audit_rate': AUDIT,
                'files': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files}}
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    sets = {'mnist': mnist(), 'cifar': cifar()}; rows = []
    for name in MODELS:
        row = run(name, sets); rows.append(row)
        print('%-15s acc %.4f central %.3f ms (%s) verify %.3f audit %.3f  L0 %.2f  L8 %.2f  trace %d B weights %d B'
              % (name, row['quantized_accuracy'], row['central_ms'], row['central_backend'], row['verify_ms'], row['audit_ms'],
                 row['leverage_no_audit'], row['leverage_8pct'], row['trace_bytes'], row['weight_bytes']), flush=True)
    (OUT / 'results.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
