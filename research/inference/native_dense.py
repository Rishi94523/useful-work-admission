"""Typed boundary for the fused dense-network kernel (amendment 15b).

Built from a prepared QuantizedNet whose sketches are the portable Sketch
objects, so the projections are the same secret ones the reference verifier
uses. Only dense (non-convolutional) networks are supported.
"""
import ctypes
import hashlib
from pathlib import Path
import numpy as np

DLL = Path(__file__).resolve().parents[2] / 'tmp/native-verifier/dense_check.dll'


def _ptr(kind): return np.ctypeslib.ndpointer(kind, flags='C_CONTIGUOUS')


class NativeDense:
    def __init__(self, q):
        ops = q.ops
        if any(op.conv for op in ops): raise ValueError('Dense networks only')
        self.q = q; self.layers = len(ops)
        self.dims = np.array([int(np.prod(ops[0].input_shape))] + [op.output_shape[0] for op in ops], dtype=np.int32)
        self.width = int(self.dims[1:].sum())
        cat = lambda parts, kind: np.ascontiguousarray(np.concatenate([np.asarray(p).ravel() for p in parts]), dtype=kind)
        self.w = cat([op.weight.numpy().astype(np.int8) for op in ops], np.int8)
        self.bias = cat([op.bias.numpy().astype(np.int32) for op in ops], np.int32)
        self.s = cat([sk.s.full.T for sk in q.sketches], np.uint32)          # in x 4, interleaved
        self.r = cat([sk.r.full.T for sk in q.sketches], np.uint32)          # out x 4, interleaved
        self.rb = cat([sk.rb for sk in q.sketches], np.uint32)
        self.bounds = cat([sk.bounds for sk in q.sketches], np.int64)
        self.mult = cat([op.multiplier if op.multiplier is not None else np.zeros(op.output_shape[0], np.int64) for op in ops], np.int64)
        self.final_scale = ops[-1].final_scale
        for a in (self.w, self.bias, self.s, self.r, self.rb, self.bounds, self.mult): a.flags.writeable = False
        lib = ctypes.CDLL(str(DLL)); self._lib = lib
        self._verify = lib.dense_verify
        self._verify.argtypes = [ctypes.c_int, _ptr(np.int32), _ptr(np.uint32), _ptr(np.uint32), _ptr(np.uint32), _ptr(np.int64), _ptr(np.int64),
                                 _ptr(np.int8), _ptr(np.int32), _ptr(np.int32), ctypes.c_size_t]
        self._verify.restype = ctypes.c_int
        self._forward = lib.dense_forward
        self._forward.argtypes = [ctypes.c_int, _ptr(np.int32), _ptr(np.int8), _ptr(np.int32), _ptr(np.int64), _ptr(np.int8),
                                  ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        self._forward.restype = ctypes.c_int

    def inputs(self, images):
        return np.ascontiguousarray(np.clip(np.rint(images / self.q.input_scale), -127, 127).reshape(len(images), -1), dtype=np.int8)

    def forward(self, images):
        """Exact trace (input-major int32 bytes) of a batch: the native central baseline."""
        x = self.inputs(images); trace = np.empty(len(images) * self.width, dtype=np.int32)
        ok = self._forward(self.layers, self.dims, self.w, self.bias, self.mult, x, trace.ctypes.data, None, len(images))
        assert ok
        return trace.astype('<i4').tobytes()

    def verify(self, images, blob, audit=False):
        """Returns (accepted, logits). Hash, parse, projections, requantisation;
        with audit, also the exact recomputation of every layer."""
        batch = len(images)
        if len(blob) != batch * self.width * 4: return False, None
        hashlib.sha256(blob).digest()
        trace = np.frombuffer(blob, dtype='<i4'); x = self.inputs(images)
        logits = np.empty(batch * int(self.dims[-1]), dtype=np.int32)
        if not self._verify(self.layers, self.dims, self.s, self.r, self.rb, self.bounds, self.mult, x, trace, logits, batch): return False, None
        if audit and not self._forward(self.layers, self.dims, self.w, self.bias, self.mult, x, None, trace.ctypes.data, batch): return False, None
        return True, logits.reshape(batch, -1) * self.final_scale
