"""Workloads for the verification-leverage study (amendment 14).

Datasets and checkpoints live in ignored data/ folders and are checked against
workload_provenance.json. Models other than the pretrained VGG11-BN are trained
by scripts/train_inference_models.py with fixed seeds and saved as state dicts.
"""
import gzip
import hashlib
import json
from pathlib import Path
import tarfile
import numpy as np
import torch
from torch import nn

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data'
TRAINED = DATA / 'inference-models'
CIFAR_MEAN = np.array([0.4914, 0.4822, 0.4465], dtype=np.float32)[None, :, None, None]
CIFAR_STD = np.array([0.2023, 0.1994, 0.2010], dtype=np.float32)[None, :, None, None]


def verify_assets():
    provenance = json.loads((Path(__file__).parent / 'workload_provenance.json').read_text())
    for asset in provenance['assets']:
        path = ROOT / asset['path']
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
            raise ValueError('Research asset changed: ' + asset['path'])


def _idx(path):
    raw = gzip.decompress(path.read_bytes())
    dims = raw[3]; shape = [int.from_bytes(raw[4 + 4 * i:8 + 4 * i], 'big') for i in range(dims)]
    return np.frombuffer(raw, dtype=np.uint8, offset=4 + 4 * dims).reshape(shape)


def mnist():
    norm = lambda x: ((x.astype(np.float32) / 255 - 0.1307) / 0.3081)[:, None]
    return {'train': (norm(_idx(DATA / 'mnist/train-images-idx3-ubyte.gz')), _idx(DATA / 'mnist/train-labels-idx1-ubyte.gz').astype(np.int64)),
            'test': (norm(_idx(DATA / 'mnist/t10k-images-idx3-ubyte.gz')), _idx(DATA / 'mnist/t10k-labels-idx1-ubyte.gz').astype(np.int64))}


def cifar():
    archive = DATA / 'cifar10/cifar-10-binary.tar.gz'
    norm = lambda x: np.ascontiguousarray((x.astype(np.float32) / 255 - CIFAR_MEAN) / CIFAR_STD)
    with tarfile.open(archive, 'r:gz') as tar:
        batches = [np.frombuffer(tar.extractfile(f'cifar-10-batches-bin/data_batch_{i}.bin').read(), dtype=np.uint8).reshape(10000, 3073) for i in range(1, 6)]
        test = np.frombuffer(tar.extractfile('cifar-10-batches-bin/test_batch.bin').read(), dtype=np.uint8).reshape(10000, 3073)
    train = np.concatenate(batches)
    new = np.load(DATA / 'journal-workloads/cifar10.1_v6_data.npy', allow_pickle=False)
    labels = np.load(DATA / 'journal-workloads/cifar10.1_v6_labels.npy', allow_pickle=False)
    return {'train': (norm(train[:, 1:].reshape(-1, 3, 32, 32)), train[:, 0].astype(np.int64)),
            'test': (norm(test[:, 1:].reshape(-1, 3, 32, 32)), test[:, 0].astype(np.int64)),
            'cifar10_1': (norm(new.transpose(0, 3, 1, 2)), labels.astype(np.int64))}


def conv_block(i, o, pool): return [nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU()] + ([nn.MaxPool2d(2)] if pool else [])


ARCHITECTURES = {
    'mnist-mlp': lambda: nn.Sequential(nn.Flatten(), nn.Linear(784, 128), nn.ReLU(), nn.Linear(128, 64), nn.ReLU(), nn.Linear(64, 10)),
    'mnist-cnn': lambda: nn.Sequential(*conv_block(1, 8, True), *conv_block(8, 16, True), nn.Flatten(), nn.Linear(784, 64), nn.ReLU(), nn.Linear(64, 10)),
    'cifar-cnn': lambda: nn.Sequential(*conv_block(3, 16, True), *conv_block(16, 32, True), *conv_block(32, 64, True), nn.Flatten(),
                                       nn.Linear(1024, 128), nn.ReLU(), nn.Linear(128, 10)),
    'mnist-wide-mlp': lambda: nn.Sequential(nn.Flatten(), nn.Linear(784, 2048), nn.ReLU(), nn.Linear(2048, 2048), nn.ReLU(), nn.Linear(2048, 10)),
}
DATASET = {'mnist-mlp': 'mnist', 'mnist-cnn': 'mnist', 'cifar-cnn': 'cifar', 'mnist-wide-mlp': 'mnist', 'vgg11-bn': 'cifar'}
INPUT_SHAPE = {'mnist-mlp': (784,), 'mnist-cnn': (1, 28, 28), 'cifar-cnn': (3, 32, 32), 'mnist-wide-mlp': (784,), 'vgg11-bn': (3, 32, 32)}


def load_trained(name):
    model = ARCHITECTURES[name]()
    model.load_state_dict(torch.load(TRAINED / f'{name}.pt', map_location='cpu', weights_only=True), strict=True)
    return model.eval()


def load_vgg():
    from research.inference.vendor.cifar_models.vgg import cifar10_vgg11_bn
    model = cifar10_vgg11_bn(pretrained=False)
    model.load_state_dict(torch.load(DATA / 'journal-workloads/cifar10_vgg11_bn-eaeebf42.pt', map_location='cpu', weights_only=True), strict=True)
    return model.eval()
