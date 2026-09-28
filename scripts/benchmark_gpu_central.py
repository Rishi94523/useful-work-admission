"""Amendment 15 secondary baseline: the server's inference of the same models
on its GPU, FP32 and FP16, timed end to end (host-to-device copy of the input
batch, forward pass, device-to-host copy of the logits, synchronised). Runs in
the separate CUDA environment tmp/gpu-models so the CPU environment of the
recorded results is unchanged.
"""
import copy
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from research.inference.workloads import DATASET, load_trained, load_vgg, mnist, cifar, verify_assets

OUT = ROOT / 'local-research/batched-leverage-2026-09-28'
PROTOCOL_COMMIT = 'fbe767f'
MODELS = ['mnist-mlp', 'mnist-cnn', 'cifar-cnn', 'mnist-wide-mlp', 'vgg11-bn']
BATCHES = [1, 8, 32, 128]
WARMUP = 20; TIMED = 64


def main():
    assert torch.cuda.is_available(), 'CUDA required'
    committed = subprocess.check_output(['git', 'show', PROTOCOL_COMMIT + ':docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'], cwd=ROOT)
    assert committed.replace(b'\r\n', b'\n') in (ROOT / 'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md').read_bytes().replace(b'\r\n', b'\n'), 'Protocol not committed'
    verify_assets(); OUT.mkdir(parents=True, exist_ok=True)
    torch.backends.cudnn.benchmark = True
    sets = {'mnist': mnist(), 'cifar': cifar()}; rng = np.random.default_rng(20260928); rows = []
    for name in MODELS:
        data = sets[DATASET[name]]; test_x = (data['cifar10_1'] if name == 'vgg11-bn' else data['test'])[0]
        base = (load_vgg() if name == 'vgg11-bn' else load_trained(name)).cuda().eval()
        models = {'fp32': (base, torch.float32), 'fp16': (copy.deepcopy(base).half(), torch.float16)}   # half() is in place
        for batch in BATCHES:
            med = {}
            for kind, (model, dtype) in models.items():
                times = []
                with torch.inference_mode():
                    for rep in range(WARMUP + TIMED):
                        host = torch.from_numpy(test_x[rng.choice(len(test_x), size=batch, replace=False)])
                        torch.cuda.synchronize(); b = time.perf_counter_ns()
                        out = model(host.to('cuda', non_blocking=False).to(dtype)).float().cpu()
                        torch.cuda.synchronize(); t = (time.perf_counter_ns() - b) / 1e6
                        if rep >= WARMUP: times.append(t)
                med[kind] = float(np.median(times))
            best = min(med, key=med.get)
            rows.append({'model': name, 'batch': batch, 'median_ms': med, 'gpu_central_ms': med[best], 'gpu_backend': best})
            print('%-15s B=%-4d fp32 %.3f ms  fp16 %.3f ms' % (name, batch, med['fp32'], med['fp16']), flush=True)
    meta = {'protocol_commit': PROTOCOL_COMMIT, 'device': torch.cuda.get_device_name(0), 'torch': torch.__version__,
            'cuda': torch.version.cuda, 'python': sys.version, 'platform': platform.platform(), 'warmup': WARMUP, 'timed': TIMED}
    (OUT / 'gpu_central.json').write_text(json.dumps({'meta': meta, 'rows': rows}, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
