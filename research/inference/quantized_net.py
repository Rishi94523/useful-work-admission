"""Exact-integer inference with prepared Freivalds checks, for any sequential
classifier built from 3x3 same-padding convolutions (with batch norm, ReLU and
optional 2x2 max pooling) followed by dense layers (with optional ReLU).

Generalised from the project's earlier QuantizedVGG so that every workload in
the leverage study is verified by the same code. Quantization and prepared
affine checks (Freivalds, Slalom) are established methods; nothing here is a
new primitive. Weights are per-channel int8, activations signed 7-bit, and each
affine output is checked with four secret projections over the field of size
2^31 - 1; ReLU, requantization and pooling are recomputed by the verifier.
"""
from dataclasses import dataclass
import hashlib
import numpy as np
import torch
import torch.nn.functional as F
from research.inference.prepared_affine import FieldRows, P, uniform_field


@dataclass
class Operator:
    name: str
    weight: torch.Tensor
    bias: torch.Tensor
    input_shape: tuple
    output_shape: tuple
    conv: bool
    pool: bool
    multiplier: np.ndarray | None
    final_scale: np.ndarray | None
    bound: np.ndarray

    def forward(self, x):
        if self.conv: return F.conv2d(x, self.weight, self.bias, padding=1)
        return F.linear(x.flatten(1), self.weight, self.bias)

    def post(self, z):
        if self.multiplier is None: return z * self.final_scale
        shape = (-1, 1, 1) if self.conv else (-1,)
        value = np.clip(np.floor((np.maximum(z, 0) * self.multiplier.reshape(shape) + 2**23) / 2**24), 0, 127).astype(np.int64)
        if self.pool:
            c, h, w = value.shape
            value = value.reshape(c, h // 2, 2, w // 2, 2).max(axis=(2, 4))
        return value

    @property
    def macs(self):
        """Multiply-accumulates of the affine operator, the work being delegated."""
        if self.conv: return int(np.prod(self.output_shape)) * self.input_shape[0] * 9
        return int(self.output_shape[0]) * int(np.prod(self.input_shape))


class Sketch:
    def __init__(self, op, rounds=4):
        self.op = op
        r = uniform_field((rounds, *op.output_shape))
        rt = torch.from_numpy(r.astype(np.float64))
        if op.conv:
            s = F.conv_transpose2d(rt, op.weight, padding=1).numpy().astype(np.int64) % P
            b = np.broadcast_to(op.bias.numpy()[:, None, None], op.output_shape).astype(np.int64).ravel()
        else:
            s = (rt @ op.weight).numpy().astype(np.int64) % P; b = op.bias.numpy().astype(np.int64)
        self.r = FieldRows(r.reshape(rounds, -1)); self.s = FieldRows(s.reshape(rounds, -1)); self.rb = self.r.dot(b)
        self.bounds = np.broadcast_to(op.bound[:, None, None], op.output_shape) if op.conv else op.bound

    def verify(self, x, z):
        if x.shape != self.op.input_shape or z.shape != self.op.output_shape or x.dtype.kind not in 'iu' or z.dtype.kind not in 'iu': return False
        if np.any(x < -127) or np.any(x > 127) or np.any(z < -self.bounds) or np.any(z > self.bounds): return False
        lhs = self.r.dot(z.ravel()); rhs = (self.s.dot_small(x.ravel()) + self.rb) % P
        return bool(np.array_equal(lhs, rhs))


def layers_from_sequential(model):
    """(weight, bias, conv, pool, relu) per affine layer of an nn.Sequential with
    Conv2d(k=3,p=1)[+BatchNorm2d]+ReLU[+MaxPool2d] blocks, Flatten, Linear[+ReLU]."""
    mods = [m for m in model.modules() if not isinstance(m, (torch.nn.Sequential,)) and m is not model]
    out = []; i = 0
    while i < len(mods):
        m = mods[i]
        if isinstance(m, torch.nn.Conv2d):
            assert m.kernel_size == (3, 3) and m.padding == (1, 1) and m.stride == (1, 1)
            w = m.weight.detach(); b = m.bias.detach() if m.bias is not None else torch.zeros(w.shape[0]); i += 1
            if i < len(mods) and isinstance(mods[i], torch.nn.BatchNorm2d):
                bn = mods[i]; scale = bn.weight.detach() / torch.sqrt(bn.running_var + bn.eps)
                w = w * scale[:, None, None, None]; b = (b - bn.running_mean) * scale + bn.bias.detach(); i += 1
            relu = mods[i] if i < len(mods) and isinstance(mods[i], torch.nn.ReLU) else None; i += 1 if relu is not None else 0
            pool = i < len(mods) and isinstance(mods[i], torch.nn.MaxPool2d); i += 1 if pool else 0
            out.append((w, b, True, pool, relu))
        elif isinstance(m, torch.nn.Linear):
            i += 1; relu = mods[i] if i < len(mods) and isinstance(mods[i], torch.nn.ReLU) else None; i += 1 if relu is not None else 0
            out.append((m.weight.detach(), m.bias.detach(), False, False, relu))
        else:
            i += 1  # Flatten, Dropout in eval mode
    return out


def layers_from_vgg(model):
    modules = list(model.features.children()); dense = [m for m in model.classifier if isinstance(m, torch.nn.Linear)]
    layers = []; i = 0
    while i < len(modules):
        conv, bn, relu = modules[i:i + 3]
        pool = i + 3 < len(modules) and isinstance(modules[i + 3], torch.nn.MaxPool2d)
        scale = bn.weight.detach() / torch.sqrt(bn.running_var + bn.eps)
        layers.append((conv.weight.detach() * scale[:, None, None, None], (conv.bias.detach() - bn.running_mean) * scale + bn.bias.detach(), True, pool, relu))
        i += 4 if pool else 3
    for j, linear in enumerate(dense):
        layers.append((linear.weight.detach(), linear.bias.detach(), False, False, None if j == 2 else model.classifier[j * 3 + 1]))
    return layers


class QuantizedNet:
    def __init__(self, model, layers, calibration, input_shape, input_scale=3.0 / 127):
        maxima = {}; handles = []
        for index, (_, _, _, _, relu) in enumerate(layers):
            if relu is not None:
                def hook(_m, _x, y, index=index): maxima[index] = max(maxima.get(index, 0), float(y.max()))
                handles.append(relu.register_forward_hook(hook))
        with torch.inference_mode():
            for start in range(0, len(calibration), 32): model(torch.from_numpy(calibration[start:start + 32]))
        for h in handles: h.remove()
        self.input_scale = input_scale; self.input_shape = tuple(input_shape)
        self.ops = []; current_scale = input_scale; shape = self.input_shape
        for index, (weight, bias, conv, pool, relu) in enumerate(layers):
            if not conv and len(shape) > 1: shape = (int(np.prod(shape)),)
            axes = tuple(range(1, weight.ndim)); wf = weight.numpy().astype(np.float64)
            scale = np.maximum(np.max(np.abs(wf), axis=axes) / 127, 1e-12)
            broad = (-1, 1, 1, 1) if conv else (-1, 1)
            wq = np.clip(np.rint(wf / scale.reshape(broad)), -127, 127).astype(np.int64)
            bq = np.rint(bias.numpy() / (current_scale * scale)).astype(np.int64)
            bound = 127 * np.abs(wq).sum(axis=axes) + np.abs(bq)
            if np.any(bound >= P // 2): raise ValueError('Output escapes unique signed field range')
            out_shape = (len(bq), shape[1], shape[2]) if conv else (len(bq),)
            if relu is not None:
                next_scale = max(maxima[index], 1e-6) / 127
                multiplier = np.rint(current_scale * scale / next_scale * 2**24).astype(np.int64)
                if np.any(bound * multiplier + 2**23 >= 2**53): raise ValueError('Unsafe requantization')
                final_scale = None
            else: multiplier = None; final_scale = current_scale * scale
            self.ops.append(Operator(f'layer_{index}', torch.from_numpy(wq.astype(np.float64)), torch.from_numpy(bq.astype(np.float64)),
                                     shape, out_shape, conv, pool, multiplier, final_scale, bound))
            shape = (out_shape[0], out_shape[1] // 2, out_shape[2] // 2) if pool else out_shape
            if relu is not None: current_scale = next_scale
        self.sketches = []

    def prepare(self):
        with torch.inference_mode(): self.sketches = [Sketch(op) for op in self.ops]

    def use_native(self):
        from research.inference.native_affine import NativeSketch
        self.sketches = [NativeSketch(s) for s in self.sketches]
        for op, sketch in zip(self.ops, self.sketches): op.post = sketch.post

    def input(self, image): return np.clip(np.rint(image / self.input_scale), -127, 127).astype(np.int64).reshape(self.input_shape)

    def trace(self, image):
        x = self.input(image); trace = []
        with torch.inference_mode():
            for op in self.ops:
                x = x.reshape(op.input_shape)
                z = op.forward(torch.from_numpy(x.astype(np.float64))[None]).numpy()[0].astype(np.int64)
                trace.append(z); x = op.post(z)
        return trace, x

    def verify(self, image, trace, audit=False):
        if len(trace) != len(self.ops) or not self.sketches: return False, None
        x = self.input(image)
        with torch.inference_mode():
            for op, sketch, z in zip(self.ops, self.sketches, trace):
                x = x.reshape(op.input_shape)
                if not sketch.verify(x, z): return False, None
                if audit:
                    direct = op.forward(torch.from_numpy(x.astype(np.float64))[None]).numpy()[0]
                    if not np.array_equal(direct, z): return False, None
                x = op.post(z)
        return True, x

    def pack(self, trace): return b''.join(z.astype('<i4').tobytes() for z in trace)

    def unpack(self, blob):
        expected = sum(int(np.prod(op.output_shape)) * 4 for op in self.ops)
        if len(blob) != expected: raise ValueError('Incorrect trace length')
        hashlib.sha256(blob).digest(); offset = 0; trace = []
        for op in self.ops:
            count = int(np.prod(op.output_shape)); trace.append(np.frombuffer(blob, dtype='<i4', count=count, offset=offset).reshape(op.output_shape)); offset += count * 4
        return trace

    def weight_bytes(self): return sum(op.weight.numel() + 4 * op.bias.numel() for op in self.ops)

    def batch_predictions(self, images, batch_size=64):
        result = []
        with torch.inference_mode():
            for start in range(0, len(images), batch_size):
                x = np.clip(np.rint(images[start:start + batch_size] / self.input_scale), -127, 127).astype(np.float64)
                for op in self.ops:
                    x = x.reshape((len(x), *op.input_shape)); z = op.forward(torch.from_numpy(x)).numpy()
                    if op.multiplier is None: x = z * op.final_scale
                    else:
                        shape = (1, -1, 1, 1) if op.conv else (1, -1)
                        x = np.clip(np.floor((np.maximum(z, 0) * op.multiplier.reshape(shape) + 2**23) / 2**24), 0, 127)
                        if op.pool:
                            n, c, h, w = x.shape; x = x.reshape(n, c, h // 2, 2, w // 2, 2).max(axis=(3, 5))
                result.extend(x.reshape(len(x), -1).argmax(1).tolist())
        return np.array(result)
