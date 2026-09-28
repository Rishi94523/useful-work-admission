"""Train the four small classifiers of the leverage study (amendment 14).

Fixed seed, CPU, Adam. Saves state dicts to data/inference-models/ (ignored)
with a JSON record of accuracy and hashes. Accuracy is reported, not tuned:
the study measures verification cost, and the models only need to be
reasonable labelling models.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import torch
from torch import nn
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from research.inference.workloads import ARCHITECTURES, DATASET, TRAINED, mnist, cifar

SEED = 20260928
EPOCHS = {'mnist-mlp': 5, 'mnist-cnn': 5, 'mnist-wide-mlp': 5, 'cifar-cnn': 20}


def train(name, data):
    torch.manual_seed(SEED); rng = np.random.default_rng(SEED)
    model = ARCHITECTURES[name](); opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    x, y = data['train']; start = time.perf_counter()
    for epoch in range(EPOCHS[name]):
        model.train(); order = rng.permutation(len(x))
        for i in range(0, len(x), 128):
            idx = order[i:i + 128]; xb = torch.from_numpy(x[idx]); yb = torch.from_numpy(y[idx])
            if DATASET[name] == 'cifar':  # random horizontal flip only
                flip = torch.from_numpy(rng.random(len(idx)) < 0.5); xb[flip] = xb[flip].flip(3)
            opt.zero_grad(); loss = nn.functional.cross_entropy(model(xb), yb); loss.backward(); opt.step()
    model.eval()
    with torch.inference_mode():
        tx, ty = data['test']; pred = torch.cat([model(torch.from_numpy(tx[i:i + 1000])).argmax(1) for i in range(0, len(tx), 1000)])
    return model, float((pred.numpy() == ty).mean()), time.perf_counter() - start


def main():
    torch.set_num_threads(8); TRAINED.mkdir(parents=True, exist_ok=True)
    sets = {'mnist': mnist(), 'cifar': cifar()}; record = {'seed': SEED, 'torch': torch.__version__, 'models': {}}
    for name in ARCHITECTURES:
        model, acc, seconds = train(name, sets[DATASET[name]])
        path = TRAINED / f'{name}.pt'; torch.save(model.state_dict(), path)
        record['models'][name] = {'epochs': EPOCHS[name], 'test_accuracy': acc, 'train_seconds': round(seconds, 1),
                                  'parameters': sum(p.numel() for p in model.parameters()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        print(name, record['models'][name], flush=True)
    (TRAINED / 'training.json').write_text(json.dumps(record, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
