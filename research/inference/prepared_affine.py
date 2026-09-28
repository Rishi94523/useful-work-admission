"""Research-only prepared exact affine verification with binary64 limb dots.

Known Freivalds/Slalom algebra, not a new verification primitive. The two-limb
implementation accelerates exact field dots with BLAS; it never substitutes a
floating tolerance for integer equality. See research/README.md for limits.
"""
from __future__ import annotations

import secrets
import numpy as np

P = 2**31 - 1
LIMB = 2**16
MAX_DOT = 2**20


def uniform_field(shape):
    """Independent uniform field entries from OS randomness, with rejection."""
    count=int(np.prod(shape));parts=[];remaining=count
    while remaining:
        raw=np.frombuffer(secrets.token_bytes(remaining*4),dtype='<u4').astype(np.int64)
        selected=raw[raw<2*P]
        parts.append(selected % P);remaining-=len(selected)
    return np.concatenate(parts).reshape(shape)


class FieldRows:
    """Read-only prepared row vectors, each with at most 2^20 field entries."""
    def __init__(self, rows):
        values = np.asarray(rows)
        if values.ndim != 2 or not 1 <= values.shape[1] <= MAX_DOT or values.dtype.kind not in 'iu':
            raise ValueError('Expected bounded integer rows')
        if values.dtype.kind == 'u' and np.any(values > np.iinfo(np.int64).max):
            raise ValueError('Unsigned input exceeds signed conversion range')
        values = np.array(values, dtype=np.int64) % P
        self.low = (values & (LIMB - 1)).astype(np.float64)
        self.high = (values >> 16).astype(np.float64)
        self.full = values.astype(np.float64)
        self.low.flags.writeable = self.high.flags.writeable = self.full.flags.writeable = False
        self.width = values.shape[1]

    def dot(self, vector):
        values = np.asarray(vector)
        if values.shape != (self.width,) or values.dtype.kind not in 'iu':
            raise ValueError('Expected an integer vector of the prepared width')
        if values.dtype.kind == 'u' and np.any(values > np.iinfo(np.int64).max):
            raise ValueError('Unsigned input exceeds signed conversion range')
        values = values.astype(np.int64) % P
        low = (values & (LIMB - 1)).astype(np.float64)
        high = (values >> 16).astype(np.float64)
        # Each nonnegative sum is < 2^52. Every multiplication/addition is
        # exactly representable in binary64, independent of reduction order.
        a = (self.low @ low).astype(np.int64) % P
        b = ((self.high @ low).astype(np.int64) % P + (self.low @ high).astype(np.int64) % P) % P
        c = (self.high @ high).astype(np.int64) % P
        # 2^32 mod (2^31-1) = 2. Reduce BEFORE lifting limb powers.
        return (a + LIMB * b + 2 * c) % P

    def dot_small(self,vector):
        """Exact optimized path for already bounded signed 7-bit activations."""
        x=np.asarray(vector)
        if x.shape!=(self.width,) or x.dtype.kind not in 'iu' or np.any(x < -127) or np.any(x > 127):
            raise ValueError('Expected signed 7-bit activations')
        x=x.astype(np.float64);result=np.zeros(self.full.shape[0],dtype=np.int64)
        # 32768*127*(P-1) < 2^53 bounds absolute sums even with cancellation.
        for start in range(0,self.width,32768):
            partial=self.full[:,start:start+32768]@x[start:start+32768]
            result=(result+partial.astype(np.int64)%P)%P
        return result


class PreparedAffine:
    """Verify z=xW+b, x uint8, W signed int8, fixed W, four checks by default.

    The caller must keep projections private, enforce an epoch/query limit,
    authenticate assignment/model/input, and handle audits/nonlinear/state.
    This class only returns an affine-result decision and does not issue credit.
    """
    def __init__(self, weights, bias, *, rounds=4):
        w, b = np.asarray(weights), np.asarray(bias)
        if w.ndim != 2 or b.shape != (w.shape[1],) or not 1 <= rounds <= 16:
            raise ValueError('Invalid affine shape or rounds')
        if not 1 <= w.shape[0] <= 16384 or not 1 <= w.shape[1] <= 32768:
            raise ValueError('Unsupported exact arithmetic dimensions')
        if w.dtype.kind not in 'iu' or b.dtype.kind not in 'iu' or np.any(w < -128) or np.any(w > 127):
            raise ValueError('Expected signed int8 weights and integer biases')
        if np.any(b <= -P//2) or np.any(b >= P//2):
            raise ValueError('Bias outside signed field interval')
        w, b = w.astype(np.int64), b.astype(np.int64)
        self.bounds = 255 * np.abs(w).sum(axis=0) + np.abs(b)
        if np.any(self.bounds >= P//2):
            raise ValueError('Output bound does not have a unique field representation')
        self.input_size, self.output_size = w.shape
        r = uniform_field((rounds, self.output_size))
        self.rows = FieldRows(r)
        # Absolute partial sums <= 32768*128*(P-1) < 2^53: exact BLAS setup.
        projected = (r.astype(np.float64) @ w.astype(np.float64).T).astype(np.int64) % P
        self.projected = projected.astype(np.float64)
        self.bias = self.rows.dot(b)
        self.projected.flags.writeable = self.bounds.flags.writeable = self.bias.flags.writeable = False
        self.rounds = rounds

    def verify(self, inputs, claimed):
        x, z = np.asarray(inputs), np.asarray(claimed)
        if x.shape != (self.input_size,) or z.shape != (self.output_size,):
            return False
        if x.dtype.kind not in 'iu' or z.dtype.kind not in 'iu':
            return False
        if np.any(x < 0) or np.any(x > 255) or np.any(z < -self.bounds) or np.any(z > self.bounds):
            return False
        # 16384 * 255 * (P-1) < 2^53, so this direct binary64 dot is exact.
        rhs = ((self.projected @ x.astype(np.float64)).astype(np.int64) % P + self.bias) % P
        lhs = self.rows.dot(z)
        return bool(np.array_equal(lhs, rhs))
