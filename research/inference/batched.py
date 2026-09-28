"""Batched exact verification for amendment 15.

One admission labels a batch of B inputs. The visitor uploads one trace: for
each affine layer, the B int32 outputs, layer-major. The verifier checks each
layer of the whole batch with the same four secret projections the per-input
verifier uses, now as matrix products, then range-checks, hashes and applies
the nonlinear operations over the batch. All field arithmetic is exact in
binary64 by the same bounds as prepared_affine.FieldRows; nothing here is a
new primitive.
"""
import hashlib
import numpy as np
import torch
from research.inference.prepared_affine import LIMB, P

CHUNK = 32768   # 32768 * 127 * (P - 1) < 2^53 bounds the 7-bit input products


class BatchedVerifier:
    def __init__(self, q):
        """q: a prepared QuantizedNet whose sketches are the portable Sketch objects."""
        self.q = q; self.layers = []
        for op, sk in zip(q.ops, q.sketches):
            self.layers.append({'op': op, 'r_low': sk.r.low, 'r_high': sk.r.high, 's_full': sk.s.full,
                                'rb': np.asarray(sk.rb, dtype=np.int64), 'bounds': np.ascontiguousarray(sk.bounds, dtype=np.int64).ravel(),
                                'count': int(np.prod(op.output_shape))})

    def inputs(self, images):
        return np.clip(np.rint(images / self.q.input_scale), -127, 127).astype(np.int64).reshape(len(images), -1)

    # Client side (not timed): exact batched forward pass producing the trace.
    def trace(self, images):
        x = self.inputs(images); trace = []
        with torch.inference_mode():
            for layer in self.layers:
                op = layer['op']
                z = op.forward(torch.from_numpy(x.astype(np.float64)).reshape(len(x), *op.input_shape)).numpy().reshape(len(x), -1).astype(np.int64)
                trace.append(z); x = self.post(op, z)
        return trace, x

    def pack(self, trace): return b''.join(z.astype('<i4').tobytes() for z in trace)

    def unpack(self, blob, batch):
        expected = sum(l['count'] * 4 * batch for l in self.layers)
        if len(blob) != expected: raise ValueError('Incorrect trace length')
        digest = hashlib.sha256(blob).digest(); offset = 0; trace = []
        for l in self.layers:
            n = l['count'] * batch
            trace.append(np.frombuffer(blob, dtype='<i4', count=n, offset=offset).reshape(batch, l['count'])); offset += n * 4
        return trace, digest

    @staticmethod
    def post(op, z):
        """Requantisation, ReLU and pooling over the batch; identical integer
        arithmetic to the per-input verifier (bound * multiplier + 2^23 < 2^53)."""
        if op.multiplier is None: return z.reshape(len(z), *op.output_shape) * op.final_scale
        if op.conv:
            value = z.reshape(len(z), *op.output_shape).astype(np.float64)
            value = np.clip(np.floor((np.maximum(value, 0) * op.multiplier.reshape(1, -1, 1, 1) + 2**23) / 2**24), 0, 127)
            if op.pool:
                n, c, h, w = value.shape; value = value.reshape(n, c, h // 2, 2, w // 2, 2).max(axis=(3, 5))
        else:
            value = np.clip(np.floor((np.maximum(z.astype(np.float64), 0) * op.multiplier[None] + 2**23) / 2**24), 0, 127)
        return value.astype(np.int64).reshape(len(z), -1)

    def check(self, layer, x, z):
        """Four projections of one layer for the whole batch; x (B, n) 7-bit, z (B, m)."""
        if np.any(z < -layer['bounds']) or np.any(z > layer['bounds']): return False
        xt = x.T.astype(np.float64); rhs = np.zeros((4, x.shape[0]), dtype=np.int64)
        for s in range(0, xt.shape[0], CHUNK):
            rhs = (rhs + (layer['s_full'][:, s:s + CHUNK] @ xt[s:s + CHUNK]).astype(np.int64) % P) % P
        rhs = (rhs + layer['rb'][:, None]) % P
        zp = z.T.astype(np.int64) % P
        low = (zp & (LIMB - 1)).astype(np.float64); high = (zp >> 16).astype(np.float64)
        a = (layer['r_low'] @ low).astype(np.int64) % P
        b = ((layer['r_high'] @ low).astype(np.int64) % P + (layer['r_low'] @ high).astype(np.int64) % P) % P
        c = (layer['r_high'] @ high).astype(np.int64) % P
        lhs = (a + LIMB * b + 2 * c) % P
        return bool(np.array_equal(lhs, rhs))

    def verify(self, images, blob, audit=False):
        """Returns (accepted, logits). The server knows the images it assigned."""
        try: trace, _ = self.unpack(blob, len(images))
        except ValueError: return False, None
        x = self.inputs(images)
        with torch.inference_mode():
            for layer, z in zip(self.layers, trace):
                if not self.check(layer, x, z): return False, None
                if audit:
                    op = layer['op']
                    direct = op.forward(torch.from_numpy(x.astype(np.float64)).reshape(len(x), *op.input_shape)).numpy().reshape(len(x), -1)
                    if not np.array_equal(direct, z): return False, None
                x = self.post(layer['op'], z)
        return True, x
