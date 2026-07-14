"""
Plug-and-play model store.

Loads trained models from ``models/<name>/manifest.json`` + ``weights.npz``.
Each model declares its layers, labels, preprocessing and REAL SHA-256
checksums (one per layer over the exact wire bytes, plus a model checksum
that is a hash of the layer checksums, so clients holding only a segment of
the model can still verify integrity).

Layer model
-----------
A model is a sequence of PROVABLE layers. Each provable layer is an affine
operator ``z = L·x + b`` — dense (L = matmul) or conv2d (L = convolution) —
followed by a chain of cheap, server-applied POST-OPS (relu, softmax,
maxpool2d, flatten). Clients compute and submit the pre-activation ``z`` of
each provable layer; the server verifies ``z`` with secret projections (see
proof_verifier) and applies the post-ops itself to produce the next layer's
input. Because every provable layer is affine, the same projection identity

    r · z  =  (Lᵀ r) · x  +  r · b

verifies dense and convolutional work alike, so new architectures only need
to implement ``forward`` and ``project``.

Adding a new dataset/model to the system means dropping a new manifest +
weights directory into ``models/`` — no code changes required for any
combination of dense and conv2d layers.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# models/ directory at the repository root (server/ is the CWD in dev)
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[3] / "models"

# Prime modulus for EXACT Freivalds verification of quantized layers.
# 2^31 - 1 (Mersenne). A fabricated integer output vector passes a single
# secret projection with probability 1/p ≈ 4.7e-10; with 4 projections the
# soundness error is ~2^-124 — cryptographic-grade, with NO float tolerance
# and no need for spot audits.
MOD_P = 2**31 - 1


def dot_mod(a, b, p: int = MOD_P) -> int:
    """Exact dot product of two integer sequences, reduced mod p."""
    return int(sum(int(x) * int(y) for x, y in zip(a, b)) % p)


# ---------------------------------------------------------------------------
# Post-ops: cheap O(n) transforms the server applies between provable layers
# ---------------------------------------------------------------------------

def apply_post_ops(
    z: np.ndarray, post_ops: Sequence[dict], layer_input: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Apply a layer's post-op chain to its flat pre-activation vector.

    Every op is O(n) — orders of magnitude cheaper than the affine layer the
    client computed — so the server can run them during verification without
    giving up the compute asymmetry. Mirrored exactly by the browser client.
    ``layer_input`` is the layer's own input, needed for residual connections.
    """
    h = np.asarray(z, dtype=np.float64)
    for op in post_ops:
        kind = op["op"]
        if kind == "relu":
            h = np.maximum(h, 0.0)
        elif kind == "softmax":
            shifted = h - np.max(h)
            e = np.exp(shifted)
            h = e / e.sum()
        elif kind == "sigmoid":
            h = 1.0 / (1.0 + np.exp(-h))
        elif kind == "tanh":
            h = np.tanh(h)
        elif kind == "maxpool2d":
            c, height, width = op["shape"]
            pool = int(op.get("pool", 2))
            oh, ow = height // pool, width // pool
            t = h.reshape(c, height, width)[:, : oh * pool, : ow * pool]
            t = t.reshape(c, oh, pool, ow, pool)
            h = t.max(axis=(2, 4)).reshape(-1)
        elif kind == "flatten":
            h = h.reshape(-1)
        elif kind == "requantize":
            # Exact integer rescale: a = min(max_val, (z*mult + half) >> shift).
            # Values stay < 2^53 so float64 arithmetic on them is exact and
            # browser clients (JS numbers) reproduce it bit-for-bit.
            mult = int(op["mult"])
            shift = int(op["shift"])
            max_val = int(op.get("max", 255))
            half = float(2 ** (shift - 1))
            h = np.minimum(np.floor((h * mult + half) / float(2**shift)), max_val)
        elif kind == "dequantize":
            h = h * float(op["scale"])
        elif kind == "residual_input":
            if layer_input is None:
                raise ValueError("residual_input post-op requires the layer input")
            h = h + np.asarray(layer_input, dtype=np.float64)
        elif kind == "mean_pool_tokens":
            seq, dim = int(op["seq"]), int(op["dim"])
            h = h.reshape(seq, dim).mean(axis=0)
        elif kind == "rmsnorm":
            seq = int(op.get("seq", 1))
            weight = np.asarray(op["weight"], dtype=np.float64)
            eps = float(op.get("eps", 1e-6))
            t = h.reshape(seq, -1) if seq > 1 else h.reshape(1, -1)
            variance = np.mean(t * t, axis=-1, keepdims=True)
            h = (t / np.sqrt(variance + eps) * weight).reshape(h.shape)
        elif kind == "last_token":
            seq, dim = int(op["seq"]), int(op["dim"])
            h = h.reshape(seq, dim)[-1]
        elif kind == "linear":
            pass
        else:
            raise ValueError(f"unknown post-op {kind!r}")
    return h


def post_ops_output_size(input_size: int, post_ops: Sequence[dict]) -> int:
    """Flat size after applying a post-op chain to ``input_size`` elements."""
    size = input_size
    for op in post_ops:
        if op["op"] == "maxpool2d":
            c, height, width = op["shape"]
            pool = int(op.get("pool", 2))
            size = c * (height // pool) * (width // pool)
    return size


# ---------------------------------------------------------------------------
# Provable layers
# ---------------------------------------------------------------------------

@dataclass
class DenseLayer:
    """A dense affine layer ``z = x·W + b`` with its wire-format checksum."""

    index: int
    name: str
    activation: str
    input_size: int
    output_size: int
    weights: np.ndarray  # shape (input_size, output_size), float32
    biases: np.ndarray  # shape (output_size,), float32
    checksum: str
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "dense"

    def __post_init__(self) -> None:
        if not self.post_ops and self.activation and self.activation != "linear":
            self.post_ops = [{"op": self.activation}]

    @property
    def compute_ops(self) -> int:
        """Multiply-accumulates the client spends on this layer."""
        return self.input_size * self.output_size

    @property
    def projection_ops(self) -> int:
        """Multiplications per secret-projection check (O(in + out))."""
        return self.input_size + self.output_size

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Reference pre-activation (float64). Used for audits/tests only."""
        return np.asarray(x, dtype=np.float64) @ self.weights.astype(
            np.float64
        ) + self.biases.astype(np.float64)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Freivalds precomputation: return (s, r·b) with s = Lᵀr = W·r so that
        r·z = s·x + r·b for any honest z = x·W + b.
        """
        w = self.weights.astype(np.float64)
        b = self.biases.astype(np.float64)
        return w @ r, float(r @ b)

    def wire_payload(self) -> dict:
        """
        JSON payload the browser executes. Weights are flattened in
        (output, input) row-major order to match the client's
        ``weights[o * inputSize + i]`` indexing.
        """
        return {
            "name": self.name,
            "type": "dense",
            "weights": np.ascontiguousarray(self.weights.T, dtype=np.float32)
            .flatten()
            .tolist(),
            "biases": self.biases.astype(np.float32).tolist(),
            "inputShape": [1, self.input_size],
            "outputShape": [1, self.output_size],
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        """SHA-256 over the exact float32 LE bytes a client receives."""
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights.T, dtype="<f4").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<f4").tobytes())
        return h.hexdigest()


@dataclass
class Conv2DLayer:
    """
    A valid (no padding), stride-1 2D convolution ``z = W * x + b``.

    Tensors are flattened channel-major (C, H, W) row-major on the wire and in
    pipeline handoffs. Weights are stored (out_ch, in_ch, kh, kw); the wire
    flattening ``weights[((oc*inCh + ic)*kh + u)*kw + v]`` matches the dense
    layer's output-major convention.
    """

    index: int
    name: str
    activation: str
    in_channels: int
    out_channels: int
    kernel: Tuple[int, int]
    input_shape: Tuple[int, int, int]  # (in_ch, H, W)
    weights: np.ndarray  # (out_ch, in_ch, kh, kw), float32
    biases: np.ndarray  # (out_ch,), float32
    checksum: str
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "conv2d"

    def __post_init__(self) -> None:
        if not self.post_ops and self.activation and self.activation != "linear":
            self.post_ops = [{"op": self.activation}]

    @property
    def output_shape(self) -> Tuple[int, int, int]:
        _, height, width = self.input_shape
        kh, kw = self.kernel
        return (self.out_channels, height - kh + 1, width - kw + 1)

    @property
    def input_size(self) -> int:
        return int(np.prod(self.input_shape))

    @property
    def output_size(self) -> int:
        return int(np.prod(self.output_shape))

    @property
    def compute_ops(self) -> int:
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        return oh * ow * oc * self.in_channels * kh * kw

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Reference pre-activation (float64, flat). Audits/tests only."""
        c, height, width = self.input_shape
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        x3 = np.asarray(x, dtype=np.float64).reshape(c, height, width)
        w = self.weights.astype(np.float64)
        z = np.zeros((oc, oh, ow))
        for u in range(kh):
            for v in range(kw):
                patch = x3[:, u : u + oh, v : v + ow]
                z += np.tensordot(w[:, :, u, v], patch, axes=(1, 0))
        z += self.biases.astype(np.float64)[:, None, None]
        return z.reshape(-1)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Freivalds precomputation for convolution: s = Lᵀr is the transposed
        convolution of r with the kernels (computed ONCE per model version),
        after which each verification is a single O(in)+O(out) dot product —
        the asymmetry grows with kernel size × channels.
        """
        c, height, width = self.input_shape
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        r3 = np.asarray(r, dtype=np.float64).reshape(oc, oh, ow)
        w = self.weights.astype(np.float64)
        s3 = np.zeros((c, height, width))
        for u in range(kh):
            for v in range(kw):
                s3[:, u : u + oh, v : v + ow] += np.tensordot(
                    w[:, :, u, v], r3, axes=(0, 0)
                )
        r_dot_b = float(
            np.sum(self.biases.astype(np.float64) * r3.sum(axis=(1, 2)))
        )
        return s3.reshape(-1), r_dot_b

    def wire_payload(self) -> dict:
        return {
            "name": self.name,
            "type": "conv2d",
            "weights": np.ascontiguousarray(self.weights, dtype=np.float32)
            .flatten()
            .tolist(),
            "biases": self.biases.astype(np.float32).tolist(),
            "inputShape": list(self.input_shape),
            "outputShape": list(self.output_shape),
            "kernel": list(self.kernel),
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        """SHA-256 over the exact float32 LE bytes a client receives."""
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights, dtype="<f4").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<f4").tobytes())
        return h.hexdigest()


@dataclass
class QuantizedDenseLayer:
    """
    Int8-quantized dense layer with EXACT integer arithmetic.

    z = x_q · W_q + b_q where x_q are integer activations, W_q int8, b_q
    int32. Every value is an exact integer < 2^53, so browsers (float64 JS
    numbers) and the server agree bit-for-bit — verification needs no
    tolerance, and Freivalds runs over Z_p with soundness error 1/p per
    secret projection.
    """

    index: int
    name: str
    activation: str
    input_size: int
    output_size: int
    weights: np.ndarray  # int8 (input_size, output_size)
    biases: np.ndarray  # int32 (output_size,)
    checksum: str
    w_scale: float = 1.0  # dequant: z_true ≈ z_int * w_scale * x_scale
    x_scale: float = 1.0
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "dense"
    exact = True  # verified with exact mod-p equality, not tolerances

    @property
    def compute_ops(self) -> int:
        return self.input_size * self.output_size

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Exact integer pre-activation, returned as float64 (exact ints)."""
        xi = np.asarray(x, dtype=np.int64)
        z = xi @ self.weights.astype(np.int64) + self.biases.astype(np.int64)
        return z.astype(np.float64)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, int]:
        """Mod-p Freivalds precompute: s = W_q·r mod p, r·b mod p."""
        ri = np.asarray(r, dtype=np.int64)
        # |W|<=127, r<2^31: per-term <2^38, summed over <=2^14 terms: safe int64
        s = (self.weights.astype(np.int64) @ ri) % MOD_P
        rb = dot_mod(ri, self.biases)
        return s, rb

    def wire_payload(self) -> dict:
        return {
            "name": self.name,
            "type": "dense",
            "quantized": True,
            "weights": np.ascontiguousarray(self.weights.T, dtype=np.int8)
            .flatten()
            .tolist(),
            "biases": self.biases.astype(np.int64).tolist(),
            "inputShape": [1, self.input_size],
            "outputShape": [1, self.output_size],
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        """SHA-256 over the exact int8/int32 LE bytes a client receives."""
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights.T, dtype="<i1").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<i4").tobytes())
        return h.hexdigest()


@dataclass
class QuantizedConv2DLayer:
    """Int8-quantized valid stride-1 conv2d with exact integer arithmetic."""

    index: int
    name: str
    activation: str
    in_channels: int
    out_channels: int
    kernel: Tuple[int, int]
    input_shape: Tuple[int, int, int]
    weights: np.ndarray  # int8 (out_ch, in_ch, kh, kw)
    biases: np.ndarray  # int32 (out_ch,)
    checksum: str
    w_scale: float = 1.0
    x_scale: float = 1.0
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "conv2d"
    exact = True

    @property
    def output_shape(self) -> Tuple[int, int, int]:
        _, height, width = self.input_shape
        kh, kw = self.kernel
        return (self.out_channels, height - kh + 1, width - kw + 1)

    @property
    def input_size(self) -> int:
        return int(np.prod(self.input_shape))

    @property
    def output_size(self) -> int:
        return int(np.prod(self.output_shape))

    @property
    def compute_ops(self) -> int:
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        return oh * ow * oc * self.in_channels * kh * kw

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def forward(self, x: np.ndarray) -> np.ndarray:
        c, height, width = self.input_shape
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        x3 = np.asarray(x, dtype=np.int64).reshape(c, height, width)
        w = self.weights.astype(np.int64)
        z = np.zeros((oc, oh, ow), dtype=np.int64)
        for u in range(kh):
            for v in range(kw):
                z += np.tensordot(w[:, :, u, v], x3[:, u : u + oh, v : v + ow], axes=(1, 0))
        z += self.biases.astype(np.int64)[:, None, None]
        return z.reshape(-1).astype(np.float64)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, int]:
        c, height, width = self.input_shape
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        r3 = np.asarray(r, dtype=np.int64).reshape(oc, oh, ow)
        w = self.weights.astype(np.int64)
        s3 = np.zeros((c, height, width), dtype=np.int64)
        for u in range(kh):
            for v in range(kw):
                # |W|<=127 * r<2^31 summed over <=oc terms stays under 2^63,
                # but reduce mod p each tap to keep headroom
                s3[:, u : u + oh, v : v + ow] = (
                    s3[:, u : u + oh, v : v + ow]
                    + np.tensordot(w[:, :, u, v], r3, axes=(0, 0))
                ) % MOD_P
        rb = int(
            sum(
                int(b) * int(rs)
                for b, rs in zip(
                    self.biases.astype(np.int64), r3.sum(axis=(1, 2)) % MOD_P
                )
            )
            % MOD_P
        )
        return s3.reshape(-1), rb

    def wire_payload(self) -> dict:
        return {
            "name": self.name,
            "type": "conv2d",
            "quantized": True,
            "weights": np.ascontiguousarray(self.weights, dtype=np.int8)
            .flatten()
            .tolist(),
            "biases": self.biases.astype(np.int64).tolist(),
            "inputShape": list(self.input_shape),
            "outputShape": list(self.output_shape),
            "kernel": list(self.kernel),
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights, dtype="<i1").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<i4").tobytes())
        return h.hexdigest()


def patchify(x: np.ndarray, grid: Tuple[int, int], patch: Tuple[int, int]) -> np.ndarray:
    """Flat image -> (seq, patch_pixels) row-major patch matrix."""
    gy, gx = grid
    py, px = patch
    return (
        np.asarray(x, dtype=np.float64)
        .reshape(gy, py, gx, px)
        .transpose(0, 2, 1, 3)
        .reshape(gy * gx, py * px)
    )


def unpatchify(patches: np.ndarray, grid: Tuple[int, int], patch: Tuple[int, int]) -> np.ndarray:
    """(seq, patch_pixels) -> flat image; inverse of patchify."""
    gy, gx = grid
    py, px = patch
    return (
        np.asarray(patches, dtype=np.float64)
        .reshape(gy, gx, py, px)
        .transpose(0, 2, 1, 3)
        .reshape(gy * py * gx * px)
    )


@dataclass
class TokenDenseLayer:
    """
    Per-token dense layer (transformer patch/token embedding): every token t
    computes z_t = x_t·W + B_t with a shared W and per-token bias B (which
    absorbs the positional embedding). The whole layer is affine in the flat
    input, so the standard projection check applies unchanged; ``patchify``
    is a fixed permutation folded into the projection precompute.
    """

    index: int
    name: str
    activation: str
    seq: int
    token_input_size: int
    token_output_size: int
    weights: np.ndarray  # (token_input_size, token_output_size), float32
    biases: np.ndarray  # (seq, token_output_size), float32
    checksum: str
    post_ops: List[dict] = field(default_factory=list)
    patchify_grid: Optional[Tuple[int, int]] = None  # e.g. (4, 4)
    patchify_patch: Optional[Tuple[int, int]] = None  # e.g. (7, 7)

    layer_type = "token_dense"

    @property
    def input_size(self) -> int:
        return self.seq * self.token_input_size

    @property
    def output_size(self) -> int:
        return self.seq * self.token_output_size

    @property
    def compute_ops(self) -> int:
        return self.seq * self.token_input_size * self.token_output_size

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def _tokens(self, x: np.ndarray) -> np.ndarray:
        if self.patchify_grid:
            return patchify(x, self.patchify_grid, self.patchify_patch)
        return np.asarray(x, dtype=np.float64).reshape(self.seq, self.token_input_size)

    def forward(self, x: np.ndarray) -> np.ndarray:
        tokens = self._tokens(x)
        z = tokens @ self.weights.astype(np.float64) + self.biases.astype(np.float64)
        return z.reshape(-1)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, float]:
        r3 = np.asarray(r, dtype=np.float64).reshape(self.seq, self.token_output_size)
        s_tokens = r3 @ self.weights.astype(np.float64).T  # (seq, token_in)
        if self.patchify_grid:
            s = unpatchify(s_tokens, self.patchify_grid, self.patchify_patch)
        else:
            s = s_tokens.reshape(-1)
        r_dot_b = float(np.sum(r3 * self.biases.astype(np.float64)))
        return s, r_dot_b

    def wire_payload(self) -> dict:
        payload = {
            "name": self.name,
            "type": "token_dense",
            "seq": self.seq,
            "weights": np.ascontiguousarray(self.weights.T, dtype=np.float32)
            .flatten()
            .tolist(),
            "biases": np.ascontiguousarray(self.biases, dtype=np.float32)
            .flatten()
            .tolist(),
            "inputShape": [self.seq, self.token_input_size],
            "outputShape": [self.seq, self.token_output_size],
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }
        if self.patchify_grid:
            payload["patchify"] = {
                "grid": list(self.patchify_grid),
                "patch": list(self.patchify_patch),
            }
        return payload

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights.T, dtype="<f4").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<f4").tobytes())
        return h.hexdigest()


@dataclass
class AttentionLayer:
    """
    Single-head self-attention block. The client submits the concatenation
    [Q | K | V | S | O | Z] (all row-major, token-major):

        Q = X·Wq   K = X·Wk   V = X·Wv        (affine in the input X)
        S = Q·Kᵀ                              (bilinear — Freivalds product check)
        P = softmax(S) rowwise                (SERVER computes from verified S)
        O = P·V                               (Freivalds product check)
        Z = O·Wo                              (affine in the verified O)

    Every sub-check is O(seq·d + seq²) versus the client's O(seq·d²) matmuls.
    This is the verification path that generalizes to transformer/LLM blocks.
    The attention scale 1/√d is folded into Wq at export.
    """

    index: int
    name: str
    activation: str
    seq: int
    d_model: int
    wq: np.ndarray  # (d, d) float32, scale folded in
    wk: np.ndarray
    wv: np.ndarray
    wo: np.ndarray
    checksum: str
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "attention"

    @property
    def input_size(self) -> int:
        return self.seq * self.d_model

    @property
    def output_size(self) -> int:
        # Q, K, V, O, Z blocks of seq*d plus S of seq*seq
        return 5 * self.seq * self.d_model + self.seq * self.seq

    @property
    def compute_ops(self) -> int:
        proj = 4 * self.seq * self.d_model * self.d_model  # Q,K,V,Z matmuls
        products = 2 * self.seq * self.seq * self.d_model  # S = QKᵀ, O = PV
        return proj + products

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def offsets(self) -> dict:
        td = self.seq * self.d_model
        return {
            "Q": (0, td),
            "K": (td, 2 * td),
            "V": (2 * td, 3 * td),
            "S": (3 * td, 3 * td + self.seq * self.seq),
            "O": (3 * td + self.seq * self.seq, 4 * td + self.seq * self.seq),
            "Z": (4 * td + self.seq * self.seq, 5 * td + self.seq * self.seq),
        }

    def extract(self, z_flat: np.ndarray) -> dict:
        """Slice the submitted concatenation into named (seq, ·) matrices."""
        z = np.asarray(z_flat, dtype=np.float64)
        parts = {}
        for name, (start, end) in self.offsets().items():
            width = self.seq if name == "S" else self.d_model
            parts[name] = z[start:end].reshape(self.seq, width)
        return parts

    def z_output(self, z_flat: np.ndarray) -> np.ndarray:
        start, end = self.offsets()["Z"]
        return np.asarray(z_flat, dtype=np.float64)[start:end]

    @staticmethod
    def softmax_rows(s: np.ndarray) -> np.ndarray:
        shifted = s - s.max(axis=-1, keepdims=True)
        e = np.exp(shifted)
        return e / e.sum(axis=-1, keepdims=True)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Reference computation of the full submission concatenation."""
        xt = np.asarray(x, dtype=np.float64).reshape(self.seq, self.d_model)
        q = xt @ self.wq.astype(np.float64)
        k = xt @ self.wk.astype(np.float64)
        v = xt @ self.wv.astype(np.float64)
        s = q @ k.T
        p = self.softmax_rows(s)
        o = p @ v
        z = o @ self.wo.astype(np.float64)
        return np.concatenate(
            [q.reshape(-1), k.reshape(-1), v.reshape(-1), s.reshape(-1), o.reshape(-1), z.reshape(-1)]
        )

    def wire_payload(self) -> dict:
        return {
            "name": self.name,
            "type": "attention",
            "seq": self.seq,
            "dModel": self.d_model,
            "weights": np.concatenate(
                [
                    np.ascontiguousarray(w.T, dtype=np.float32).flatten()
                    for w in (self.wq, self.wk, self.wv, self.wo)
                ]
            ).tolist(),
            "biases": [],
            "inputShape": [self.seq, self.d_model],
            "outputShape": [self.output_size],
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        for w in (self.wq, self.wk, self.wv, self.wo):
            h.update(np.ascontiguousarray(w.T, dtype="<f4").tobytes())
        return h.hexdigest()


ProvableLayer = DenseLayer  # legacy alias; layers are duck-typed


# ---------------------------------------------------------------------------
# Model spec
# ---------------------------------------------------------------------------

@dataclass
class ModelSpec:
    """A loaded, integrity-verified model."""

    name: str
    version: str
    task_type: str
    labels: List[str]
    input_shape: List[int]
    preprocessing: str
    checksum: str
    layers: List = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    # Quantized models take integer pixel inputs (0..255) instead of 0..1
    input_quantized: bool = False
    # "image" or "text" — used to pick matching samples from the pool
    input_kind: str = "image"
    # Large text models stay opt-in so ordinary CAPTCHA traffic does not
    # unexpectedly download transformer blocks (explicit browser request only).
    auto_serve: bool = True
    # LLM text models: tokenizer + prompt template + mmap'd embedding matrix
    tokenizer_file: Optional[str] = None
    prompt_template: Optional[str] = None
    embedding_file: Optional[str] = None
    model_dir: Optional[Path] = None
    _tokenizer: Optional[object] = field(default=None, repr=False)
    _embeddings: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def total_layers(self) -> int:
        return len(self.layers)

    @property
    def input_size(self) -> int:
        return int(np.prod(self.input_shape))

    @property
    def total_compute_ops(self) -> int:
        return sum(layer.compute_ops for layer in self.layers)

    def shard_payloads(self, start: int, end: int) -> List[dict]:
        """Wire payloads (with checksums) for the layer segment [start, end)."""
        payloads = []
        for layer in self.layers[start:end]:
            wire = layer.wire_payload()
            payloads.append(
                {
                    "index": layer.index,
                    "name": layer.name,
                    "layerType": layer.layer_type,
                    "inputShape": wire["inputShape"],
                    "outputShape": wire["outputShape"],
                    "activation": layer.activation,
                    "checksum": layer.checksum,
                    "layers": [wire],
                }
            )
        return payloads

    def apply_activation(self, z: np.ndarray, activation: str) -> np.ndarray:
        """Apply a single named activation (legacy dense path)."""
        return apply_post_ops(z, [{"op": activation}] if activation else [])

    def apply_layer_post_ops(
        self, z: np.ndarray, layer_index: int, layer_input: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Apply layer ``layer_index``'s post-op chain to its pre-activation.
        For attention layers the post-ops operate on the Z sub-block of the
        submitted concatenation; ``layer_input`` feeds residual connections.
        """
        layer = self.layers[layer_index]
        if hasattr(layer, "z_output"):
            # multi-part submissions ([Q|K|V|S|O|Z], [G|U|D], …): post-ops
            # operate on the final sub-block
            z = layer.z_output(z)
        return apply_post_ops(z, layer.post_ops, layer_input=layer_input)

    def forward_segment(
        self, x: np.ndarray, start: int, end: int, pad_len: int = 0
    ) -> tuple[List[np.ndarray], np.ndarray]:
        """
        Reference forward pass over layers [start, end).

        Returns (pre_activations per layer, final post-op output). Used only
        for spot audits and tests — routine validation uses the projection
        checks in proof_verifier, which never run this. ``pad_len`` is the
        left-padding length for LLM attention masks.
        """
        from app.ml.llm_layers import GQAAttentionLayer, SwigluMlpLayer

        pre_activations: List[np.ndarray] = []
        h = np.asarray(x, dtype=np.float64)
        for offset, layer in enumerate(self.layers[start:end]):
            if isinstance(layer, (GQAAttentionLayer, SwigluMlpLayer)):
                z = layer.forward(h, pad_len=pad_len)
            else:
                z = layer.forward(h)
            pre_activations.append(z)
            h = self.apply_layer_post_ops(z, start + offset, layer_input=h)
        return pre_activations, h

    def predict(self, x: np.ndarray, pad_len: int = 0) -> np.ndarray:
        """Full forward pass returning class probabilities."""
        _, h = self.forward_segment(x, 0, self.total_layers, pad_len=pad_len)
        return h

    # -- text (LLM) input preparation ------------------------------------

    def _get_tokenizer(self):
        if self._tokenizer is None:
            from tokenizers import Tokenizer

            self._tokenizer = Tokenizer.from_file(
                str((self.model_dir or Path(".")) / self.tokenizer_file)
            )
        return self._tokenizer

    def _get_embeddings(self) -> np.ndarray:
        if self._embeddings is None:
            # float16 .npy, memory-mapped: rows are read on demand so the
            # multi-hundred-MB vocabulary never fully loads into RAM
            self._embeddings = np.load(
                (self.model_dir or Path(".")) / self.embedding_file, mmap_mode="r"
            )
        return self._embeddings

    @property
    def seq(self) -> int:
        return getattr(self.layers[0], "seq", 1)

    def tokenize_prompt(self, text: str) -> tuple[List[int], int]:
        """Format the prompt, tokenize, left-pad/truncate to ``seq``."""
        prompt = (self.prompt_template or "{text}").format(text=text.strip())
        ids = self._get_tokenizer().encode(prompt).ids
        if len(ids) > self.seq:
            ids = ids[-self.seq :]
        pad_len = self.seq - len(ids)
        # left-pad with the first prompt token; masked out of attention
        ids = [ids[0]] * pad_len + ids
        return ids, pad_len

    def prepare_input(
        self, sample_blob: Optional[bytes], sample_url: Optional[str] = None
    ) -> tuple[List[float], dict]:
        """
        Input vector + context for a new pipeline run. Image models: the
        pixel vector. Text models: token ids are embedded server-side (cheap
        lookup) and the left-pad length is returned for attention masking.
        """
        if self.input_kind == "text":
            text = (sample_blob or b"").decode("utf-8", errors="replace")
            ids, pad_len = self.tokenize_prompt(text)
            embeddings = self._get_embeddings()
            vec = np.asarray(embeddings[ids], dtype=np.float32).reshape(-1)
            return [float(v) for v in vec], {"pad_len": pad_len}
        return self.preprocess_sample(sample_blob, sample_url), {}

    def preprocess_sample(
        self, sample_blob: Optional[bytes], sample_url: Optional[str] = None
    ) -> List[float]:
        """Convert raw sample bytes into the model's input vector."""
        if sample_blob:
            try:
                if len(self.input_shape) == 3:
                    _, height, width = self.input_shape
                else:
                    height = width = int(np.sqrt(self.input_size))
                image = (
                    Image.open(io.BytesIO(sample_blob))
                    .convert("L")
                    .resize((width, height))
                )
                if self.input_quantized:
                    pixels = np.asarray(image, dtype=np.float64)
                else:
                    pixels = np.asarray(image, dtype=np.float32) / 255.0
                return pixels.flatten().tolist()
            except Exception:
                pass  # non-image blob: fall through to raw bytes

        source = sample_blob or (sample_url.encode("utf-8") if sample_url else b"")
        if self.input_quantized:
            values = [float(byte) for byte in source[: self.input_size]]
        else:
            values = [byte / 255.0 for byte in source[: self.input_size]]
        values.extend([0.0] * (self.input_size - len(values)))
        return values


def encode_input_data(input_data: Sequence[float]) -> str:
    """Encode float32 input data as base64 for the browser shard engine."""
    packed = struct.pack(f"<{len(input_data)}f", *input_data)
    return base64.b64encode(packed).decode("ascii")


def decode_input_data(encoded: str) -> List[float]:
    """Decode base64 float32 data back to a list."""
    raw = base64.b64decode(encoded)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def _load_layer(layer_manifest: dict, weights: np.lib.npyio.NpzFile):
    i = layer_manifest["index"]
    layer_type = layer_manifest.get("type", "dense")
    post_ops = list(layer_manifest.get("post_ops", []))
    quantized = bool(layer_manifest.get("quantized", False))

    if layer_type == "dense" and quantized:
        return QuantizedDenseLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest.get("activation", "linear"),
            input_size=layer_manifest["input_size"],
            output_size=layer_manifest["output_size"],
            weights=weights[f"W{i}"].astype(np.int8),
            biases=weights[f"b{i}"].astype(np.int32),
            checksum=layer_manifest["checksum"],
            w_scale=layer_manifest.get("w_scale", 1.0),
            x_scale=layer_manifest.get("x_scale", 1.0),
            post_ops=post_ops,
        )
    if layer_type == "conv2d" and quantized:
        return QuantizedConv2DLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest.get("activation", "linear"),
            in_channels=layer_manifest["in_channels"],
            out_channels=layer_manifest["out_channels"],
            kernel=tuple(layer_manifest["kernel"]),
            input_shape=tuple(layer_manifest["input_shape"]),
            weights=weights[f"W{i}"].astype(np.int8),
            biases=weights[f"b{i}"].astype(np.int32),
            checksum=layer_manifest["checksum"],
            w_scale=layer_manifest.get("w_scale", 1.0),
            x_scale=layer_manifest.get("x_scale", 1.0),
            post_ops=post_ops,
        )
    if layer_type == "dense":
        return DenseLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest["activation"],
            input_size=layer_manifest["input_size"],
            output_size=layer_manifest["output_size"],
            weights=weights[f"W{i}"].astype(np.float32),
            biases=weights[f"b{i}"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            post_ops=post_ops,
        )
    if layer_type == "conv2d":
        return Conv2DLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest.get("activation", "linear"),
            in_channels=layer_manifest["in_channels"],
            out_channels=layer_manifest["out_channels"],
            kernel=tuple(layer_manifest["kernel"]),
            input_shape=tuple(layer_manifest["input_shape"]),
            weights=weights[f"W{i}"].astype(np.float32),
            biases=weights[f"b{i}"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            post_ops=post_ops,
        )
    if layer_type == "token_dense":
        patch_cfg = layer_manifest.get("patchify") or {}
        return TokenDenseLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest.get("activation", "linear"),
            seq=layer_manifest["seq"],
            token_input_size=layer_manifest["input_size"],
            token_output_size=layer_manifest["output_size"],
            weights=weights[f"W{i}"].astype(np.float32),
            biases=weights[f"b{i}"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            post_ops=post_ops,
            patchify_grid=tuple(patch_cfg["grid"]) if patch_cfg else None,
            patchify_patch=tuple(patch_cfg["patch"]) if patch_cfg else None,
        )
    if layer_type == "attention":
        return AttentionLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest.get("activation", "linear"),
            seq=layer_manifest["seq"],
            d_model=layer_manifest["d_model"],
            wq=weights[f"W{i}q"].astype(np.float32),
            wk=weights[f"W{i}k"].astype(np.float32),
            wv=weights[f"W{i}v"].astype(np.float32),
            wo=weights[f"W{i}o"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            post_ops=post_ops,
        )
    if layer_type == "gqa_attention":
        from app.ml.llm_layers import GQAAttentionLayer

        return GQAAttentionLayer(
            index=i,
            name=layer_manifest["name"],
            seq=layer_manifest["seq"],
            d_model=layer_manifest["d_model"],
            n_heads=layer_manifest["n_heads"],
            n_kv_heads=layer_manifest["n_kv_heads"],
            head_dim=layer_manifest["head_dim"],
            rope_theta=layer_manifest["rope_theta"],
            wq=weights[f"W{i}q"].astype(np.int8),
            sq=weights[f"S{i}q"].astype(np.float32),
            wk=weights[f"W{i}k"].astype(np.int8),
            sk=weights[f"S{i}k"].astype(np.float32),
            wv=weights[f"W{i}v"].astype(np.int8),
            sv=weights[f"S{i}v"].astype(np.float32),
            wo=weights[f"W{i}o"].astype(np.int8),
            so=weights[f"S{i}o"].astype(np.float32),
            bq=weights[f"b{i}q"].astype(np.float32),
            bk=weights[f"b{i}k"].astype(np.float32),
            bv=weights[f"b{i}v"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            input_ops=list(layer_manifest.get("input_ops", [])),
            post_ops=post_ops,
        )
    if layer_type == "swiglu_mlp":
        from app.ml.llm_layers import SwigluMlpLayer

        return SwigluMlpLayer(
            index=i,
            name=layer_manifest["name"],
            seq=layer_manifest["seq"],
            d_model=layer_manifest["d_model"],
            ffn_dim=layer_manifest["ffn_dim"],
            wg=weights[f"W{i}g"].astype(np.int8),
            sg=weights[f"S{i}g"].astype(np.float32),
            wu=weights[f"W{i}u"].astype(np.int8),
            su=weights[f"S{i}u"].astype(np.float32),
            wd=weights[f"W{i}d"].astype(np.int8),
            sd=weights[f"S{i}d"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            input_ops=list(layer_manifest.get("input_ops", [])),
            post_ops=post_ops,
        )
    if layer_type == "candidate_logits":
        from app.ml.llm_layers import CandidateLogitsLayer

        return CandidateLogitsLayer(
            index=i,
            name=layer_manifest["name"],
            seq=layer_manifest["seq"],
            d_model=layer_manifest["d_model"],
            weights=weights[f"W{i}"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            input_ops=list(layer_manifest.get("input_ops", [])),
            post_ops=post_ops,
        )
    raise ValueError(f"unknown layer type {layer_type!r}")


class ModelStore:
    """Loads and serves all models found under the models directory."""

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = Path(models_dir) if models_dir else DEFAULT_MODELS_DIR
        self._models: Dict[str, ModelSpec] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        for manifest_path in sorted(self.models_dir.glob("*/manifest.json")):
            try:
                spec = self._load_model(manifest_path)
                self._models[spec.name] = spec
                logger.info(
                    "Loaded model %s v%s (%d layers, checksum %s…)",
                    spec.name,
                    spec.version,
                    spec.total_layers,
                    spec.checksum[:12],
                )
            except Exception as exc:
                logger.error("Failed to load model at %s: %s", manifest_path, exc)
        self._loaded = True
        if not self._models:
            raise RuntimeError(
                f"No models found in {self.models_dir}. "
                "Run scripts/train_mnist_numpy.py first."
            )

    def _load_model(self, manifest_path: Path) -> ModelSpec:
        with open(manifest_path) as f:
            manifest = json.load(f)

        model_dir = manifest_path.parent
        weights_path = model_dir / manifest["weights_file"]

        # Verify the weights file is exactly the one the manifest was built from
        actual_file_hash = hashlib.sha256(weights_path.read_bytes()).hexdigest()
        expected_file_hash = manifest.get("weights_file_sha256")
        if expected_file_hash and actual_file_hash != expected_file_hash:
            raise ValueError(f"weights file hash mismatch for {manifest['name']}")

        weights = np.load(weights_path)
        layers = []
        for layer_manifest in manifest["layers"]:
            layer = _load_layer(layer_manifest, weights)
            # Verify each layer's declared checksum against the actual weights
            actual = layer.compute_checksum()
            if actual != layer.checksum:
                raise ValueError(
                    f"layer checksum mismatch for {manifest['name']} "
                    f"layer {layer.index}"
                )
            layers.append(layer)

        # Model checksum = hash of layer checksums (verify it too)
        expected_model_checksum = hashlib.sha256(
            "".join(l.checksum for l in layers).encode("ascii")
        ).hexdigest()
        if expected_model_checksum != manifest["checksum"]:
            raise ValueError(f"model checksum mismatch for {manifest['name']}")

        return ModelSpec(
            name=manifest["name"],
            version=manifest["version"],
            task_type=manifest["task_type"],
            labels=manifest["labels"],
            input_shape=manifest["input"]["shape"],
            preprocessing=manifest["input"].get("preprocessing", ""),
            checksum=manifest["checksum"],
            layers=layers,
            metrics=manifest.get("metrics", {}),
            input_quantized=bool(manifest["input"].get("quantized", False)),
            input_kind=manifest["input"].get("kind", "image"),
            auto_serve=bool(manifest.get("pipeline", {}).get("auto_serve", True)),
            tokenizer_file=manifest["input"].get("tokenizer_file"),
            prompt_template=manifest["input"].get("prompt_template"),
            embedding_file=manifest["input"].get("embedding_file"),
            model_dir=model_dir,
        )

    def get(self, name: str) -> Optional[ModelSpec]:
        self.load()
        return self._models.get(name)

    def get_default(self) -> ModelSpec:
        self.load()
        if "mnist-tiny" in self._models:
            return self._models["mnist-tiny"]
        return next(iter(self._models.values()))

    def list_models(self) -> List[ModelSpec]:
        self.load()
        return list(self._models.values())


_store: Optional[ModelStore] = None


def get_model_store() -> ModelStore:
    """Get or create the global model store."""
    global _store
    if _store is None:
        _store = ModelStore()
        _store.load()
    return _store


def reset_model_store() -> None:
    """Reset the global store (for tests)."""
    global _store
    _store = None
