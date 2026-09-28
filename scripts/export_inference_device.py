"""Export public int8 weights, fixed inputs and expected trace hashes for the
phone inference page (amendment 14). No verifier secrets are exported: the
page times honest computation and reports trace hashes, which the analysis
compares with the expected values offline.
"""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from research.inference.quantized_net import QuantizedNet, layers_from_sequential, layers_from_vgg
from research.inference.workloads import DATASET, INPUT_SHAPE, load_trained, load_vgg, mnist, cifar

OUT = ROOT / 'tmp/vina-cdn/public/inference'
MODELS = ['mnist-mlp', 'mnist-cnn', 'cifar-cnn', 'mnist-wide-mlp', 'vgg11-bn']
INPUTS = [0, 1, 2]


def main():
    torch.set_num_threads(4); sets = {'mnist': mnist(), 'cifar': cifar()}; index = []
    for name in MODELS:
        data = sets[DATASET[name]]; model = load_vgg() if name == 'vgg11-bn' else load_trained(name)
        layers = layers_from_vgg(model) if name == 'vgg11-bn' else layers_from_sequential(model)
        q = QuantizedNet(model, layers, data['train'][0][:256], INPUT_SHAPE[name])
        test_x = data['cifar10_1'][0] if name == 'vgg11-bn' else data['test'][0]
        folder = OUT / name; folder.mkdir(parents=True, exist_ok=True); ops = []
        for i, op in enumerate(q.ops):
            (folder / f'w{i}.bin').write_bytes(op.weight.numpy().astype(np.int8).tobytes())
            (folder / f'b{i}.bin').write_bytes(op.bias.numpy().astype('<i4').tobytes())
            ops.append({'input_shape': list(op.input_shape), 'output_shape': list(op.output_shape), 'conv': op.conv, 'pool': op.pool,
                        'multiplier': op.multiplier.tolist() if op.multiplier is not None else None,
                        'final_scale': op.final_scale.tolist() if op.final_scale is not None else None})
        inputs = []
        for k in INPUTS:
            x = q.input(test_x[k]); trace, logits = q.trace(test_x[k])
            (folder / f'input{k}.bin').write_bytes(x.astype(np.int8).tobytes())
            inputs.append({'file': f'input{k}.bin', 'trace_sha256': hashlib.sha256(q.pack(trace)).hexdigest(),
                           'label': int(np.argmax(logits)), 'trace_bytes': len(q.pack(trace))})
        (folder / 'model.json').write_text(json.dumps({'name': name, 'operators': ops, 'inputs': inputs}), encoding='utf-8')
        index.append({'name': name, 'weight_bytes': q.weight_bytes(), 'macs': sum(o.macs for o in q.ops)})
        print(name, 'weights', q.weight_bytes(), 'bytes', flush=True)
    (OUT / 'index.json').write_text(json.dumps(index), encoding='utf-8')


if __name__ == '__main__': main()
