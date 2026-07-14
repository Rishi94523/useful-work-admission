"""
Transformer (LLM) provable layers for the distributed-inference pipeline.

A decoder block decomposes into two provable units, each verified without
recomputation using the primitives the pipeline already has:

GQAAttentionLayer — client submits [Q | K | V | S | O | Z]:
    Q = RoPE(Xn·Wq + bq)   K = RoPE(Xn·Wk + bk)   V = Xn·Wv + bv
        (affine in Xn: RoPE is a fixed per-position rotation, so it folds
         into the secret-projection precompute via the inverse rotation)
    S[h] = Q[h]·K[g(h)]ᵀ            (Freivalds matrix-product check per head)
    P = softmax(mask(S/√hd))        (SERVER computes: causal + left-pad mask)
    O[h] = P[h]·V[g(h)]             (Freivalds matrix-product check per head)
    Z = O·Wo                        (affine in the verified O)
    post-op: residual_input (adds the raw block input)

SwigluMlpLayer — client submits [G | U | D]:
    G = Xn·Wg,  U = Xn·Wu           (affine in Xn)
    H = silu(G) ⊙ U                 (SERVER computes from the verified G, U)
    D = H·Wd                        (affine in the server-computed H)
    post-op: residual_input

Xn = RMSNorm(x)·w is applied to the layer input by BOTH sides ("input ops"):
the server knows x (pipeline handoff), so normalizing it costs O(n) and the
affine checks run against Xn. Weights ship as per-channel int8 + f32 scales
(weight-only quantization, ~lossless); both sides dequantize identically.

CandidateLogitsLayer — zero-shot classification head: the last token's
hidden state, RMSNorm'd, projected onto the candidate answer tokens' tied
embedding rows. A tiny dense layer, verified with the standard affine check.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


def dequantize_rows(weights_i8: np.ndarray, scales: np.ndarray) -> np.ndarray:
    """
    Per-output-channel int8 -> float32 dequantization, (out, in) layout.
    ``w[o, i] = int8[o, i] * scales[o]`` — a single correctly-rounded f32
    multiply, reproduced bit-for-bit by JS clients (f64 product of two
    f32-representable values rounded once into a Float32Array).
    """
    return weights_i8.astype(np.float32) * scales.astype(np.float32)[:, None]


def rms_norm(x: np.ndarray, weight: np.ndarray, eps: float) -> np.ndarray:
    """Row-wise RMSNorm over the last axis (float64)."""
    x = np.asarray(x, dtype=np.float64)
    variance = np.mean(x * x, axis=-1, keepdims=True)
    return x / np.sqrt(variance + eps) * np.asarray(weight, dtype=np.float64)


def rope_cos_sin(seq: int, head_dim: int, theta: float) -> Tuple[np.ndarray, np.ndarray]:
    """cos/sin tables (seq, head_dim), HF llama convention (halves repeated)."""
    inv_freq = theta ** (-np.arange(0, head_dim, 2, dtype=np.float64) / head_dim)
    angles = np.arange(seq, dtype=np.float64)[:, None] * inv_freq[None, :]
    cos = np.concatenate([np.cos(angles), np.cos(angles)], axis=-1)
    sin = np.concatenate([np.sin(angles), np.sin(angles)], axis=-1)
    return cos, sin


def rotate_half(x: np.ndarray) -> np.ndarray:
    half = x.shape[-1] // 2
    return np.concatenate([-x[..., half:], x[..., :half]], axis=-1)


def apply_rope(x: np.ndarray, cos: np.ndarray, sin: np.ndarray) -> np.ndarray:
    """x: (seq, n_heads, head_dim); cos/sin: (seq, head_dim)."""
    return x * cos[:, None, :] + rotate_half(x) * sin[:, None, :]


def silu(x: np.ndarray) -> np.ndarray:
    return x / (1.0 + np.exp(-x))


def attention_probs(
    s: np.ndarray, head_dim: int, pad_len: int
) -> np.ndarray:
    """
    softmax(mask(S/√hd)) per head. s: (n_heads, seq, seq) RAW scores as
    submitted. Causal mask plus left-padding mask (pad tokens are not
    attended by real tokens); pad rows fall back to plain causal so the
    softmax stays defined — their outputs are discarded downstream.
    """
    _, seq, _ = s.shape
    scaled = np.asarray(s, dtype=np.float64) / np.sqrt(head_dim)
    i = np.arange(seq)[:, None]
    j = np.arange(seq)[None, :]
    allowed = (j <= i) & ((j >= pad_len) | (i < pad_len))
    scaled = np.where(allowed[None, :, :], scaled, -1e30)
    shifted = scaled - scaled.max(axis=-1, keepdims=True)
    e = np.exp(shifted)
    return e / e.sum(axis=-1, keepdims=True)


@dataclass
class GQAAttentionLayer:
    """Grouped-query attention block unit (see module docstring)."""

    index: int
    name: str
    seq: int
    d_model: int
    n_heads: int
    n_kv_heads: int
    head_dim: int
    rope_theta: float
    # int8 weights in HF (out, in) layout + per-out-channel f32 scales
    wq: np.ndarray
    sq: np.ndarray
    wk: np.ndarray
    sk: np.ndarray
    wv: np.ndarray
    sv: np.ndarray
    wo: np.ndarray
    so: np.ndarray
    # biases (f32; zeros when the checkpoint has none)
    bq: np.ndarray
    bk: np.ndarray
    bv: np.ndarray
    checksum: str
    input_ops: List[dict] = field(default_factory=list)  # e.g. rmsnorm
    post_ops: List[dict] = field(default_factory=list)  # residual_input

    layer_type = "gqa_attention"
    activation = "linear"

    @property
    def q_dim(self) -> int:
        return self.n_heads * self.head_dim

    @property
    def kv_dim(self) -> int:
        return self.n_kv_heads * self.head_dim

    @property
    def input_size(self) -> int:
        return self.seq * self.d_model

    def offsets(self) -> dict:
        t, q, kv = self.seq, self.q_dim, self.kv_dim
        s_size = self.n_heads * t * t
        out = {}
        pos = 0
        for name, size in (
            ("Q", t * q),
            ("K", t * kv),
            ("V", t * kv),
            ("S", s_size),
            ("O", t * q),
            ("Z", t * self.d_model),
        ):
            out[name] = (pos, pos + size)
            pos += size
        return out

    @property
    def output_size(self) -> int:
        return self.offsets()["Z"][1]

    @property
    def compute_ops(self) -> int:
        t, d, q, kv = self.seq, self.d_model, self.q_dim, self.kv_dim
        proj = t * d * (q + 2 * kv) + t * q * d  # QKV + output proj
        products = 2 * self.n_heads * t * t * self.head_dim  # S and O
        return proj + products

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def extract(self, z_flat: np.ndarray) -> dict:
        z = np.asarray(z_flat, dtype=np.float64)
        offs = self.offsets()
        t = self.seq
        return {
            "Q": z[offs["Q"][0] : offs["Q"][1]].reshape(t, self.n_heads, self.head_dim),
            "K": z[offs["K"][0] : offs["K"][1]].reshape(t, self.n_kv_heads, self.head_dim),
            "V": z[offs["V"][0] : offs["V"][1]].reshape(t, self.n_kv_heads, self.head_dim),
            "S": z[offs["S"][0] : offs["S"][1]].reshape(self.n_heads, t, t),
            "O": z[offs["O"][0] : offs["O"][1]].reshape(t, self.q_dim),
            "Z": z[offs["Z"][0] : offs["Z"][1]].reshape(t, self.d_model),
        }

    def z_output(self, z_flat: np.ndarray) -> np.ndarray:
        start, end = self.offsets()["Z"]
        return np.asarray(z_flat, dtype=np.float64)[start:end]

    def kv_group(self, h: int) -> int:
        return h // (self.n_heads // self.n_kv_heads)

    def dequant(self, which: str) -> np.ndarray:
        w, s = {
            "q": (self.wq, self.sq),
            "k": (self.wk, self.sk),
            "v": (self.wv, self.sv),
            "o": (self.wo, self.so),
        }[which]
        return dequantize_rows(w, s)  # (out, in) f32

    def source_input(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x, dtype=np.float64).reshape(-1)

    def transformed_input(self, x: np.ndarray) -> np.ndarray:
        from app.ml.model_store import apply_post_ops

        return apply_post_ops(
            self.source_input(x), self.input_ops
        ).reshape(self.seq, self.d_model)

    def forward(self, x: np.ndarray, pad_len: int = 0) -> np.ndarray:
        """Reference computation of the full submission (float64)."""
        t, hd = self.seq, self.head_dim
        xn = self.transformed_input(x)

        q = (xn @ self.dequant("q").astype(np.float64).T + self.bq).reshape(
            t, self.n_heads, hd
        )
        k = (xn @ self.dequant("k").astype(np.float64).T + self.bk).reshape(
            t, self.n_kv_heads, hd
        )
        v = (xn @ self.dequant("v").astype(np.float64).T + self.bv).reshape(
            t, self.n_kv_heads, hd
        )

        cos, sin = rope_cos_sin(t, hd, self.rope_theta)
        q = apply_rope(q, cos, sin)
        k = apply_rope(k, cos, sin)

        s = np.empty((self.n_heads, t, t))
        for h in range(self.n_heads):
            s[h] = q[:, h, :] @ k[:, self.kv_group(h), :].T

        p = attention_probs(s, hd, pad_len)
        o = np.empty((t, self.q_dim))
        for h in range(self.n_heads):
            o[:, h * hd : (h + 1) * hd] = p[h] @ v[:, self.kv_group(h), :]

        z = o @ self.dequant("o").astype(np.float64).T
        return np.concatenate(
            [q.reshape(-1), k.reshape(-1), v.reshape(-1), s.reshape(-1), o.reshape(-1), z.reshape(-1)]
        )

    def wire_payload(self) -> dict:
        import base64

        def b64(arr, dtype):
            return base64.b64encode(
                np.ascontiguousarray(arr, dtype=dtype).tobytes()
            ).decode("ascii")

        return {
            "name": self.name,
            "type": "gqa_attention",
            "seq": self.seq,
            "dModel": self.d_model,
            "nHeads": self.n_heads,
            "nKvHeads": self.n_kv_heads,
            "headDim": self.head_dim,
            "ropeTheta": self.rope_theta,
            "weights": [],
            "biases": np.concatenate([self.bq, self.bk, self.bv]).astype(np.float32).tolist(),
            "weightsB64": b64(np.concatenate([w.reshape(-1) for w in (self.wq, self.wk, self.wv, self.wo)]), "<i1"),
            "scales": np.concatenate([self.sq, self.sk, self.sv, self.so]).astype(np.float32).tolist(),
            "inputShape": [self.seq, self.d_model],
            "outputShape": [self.output_size],
            "activation": "linear",
            "inputOps": list(self.input_ops),
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        for w in (self.wq, self.wk, self.wv, self.wo):
            h.update(np.ascontiguousarray(w, dtype="<i1").tobytes())
        for s in (self.sq, self.sk, self.sv, self.so):
            h.update(np.ascontiguousarray(s, dtype="<f4").tobytes())
        for b in (self.bq, self.bk, self.bv):
            h.update(np.ascontiguousarray(b, dtype="<f4").tobytes())
        return h.hexdigest()

    def split(self, chunk_count: int) -> List["GQAAttentionChunkLayer"]:
        """Split query/KV head groups and their output-projection columns."""
        if chunk_count < 1 or chunk_count > self.n_kv_heads:
            raise ValueError("invalid GQA chunk count")
        if self.n_kv_heads % chunk_count != 0:
            raise ValueError("GQA chunks must evenly divide KV heads")

        heads_per_kv = self.n_heads // self.n_kv_heads
        kv_per_chunk = self.n_kv_heads // chunk_count
        chunks: List[GQAAttentionChunkLayer] = []
        for chunk_index in range(chunk_count):
            kv_start = chunk_index * kv_per_chunk
            kv_end = kv_start + kv_per_chunk
            head_start = kv_start * heads_per_kv
            head_end = kv_end * heads_per_kv
            q_start, q_end = (
                head_start * self.head_dim,
                head_end * self.head_dim,
            )
            kv_dim_start, kv_dim_end = (
                kv_start * self.head_dim,
                kv_end * self.head_dim,
            )
            chunk = GQAAttentionChunkLayer(
                index=-1,
                name=f"{self.name}_part{chunk_index + 1}of{chunk_count}",
                seq=self.seq,
                d_model=self.d_model,
                n_heads=head_end - head_start,
                n_kv_heads=kv_end - kv_start,
                head_dim=self.head_dim,
                rope_theta=self.rope_theta,
                wq=np.ascontiguousarray(self.wq[q_start:q_end]),
                sq=np.ascontiguousarray(self.sq[q_start:q_end]),
                wk=np.ascontiguousarray(self.wk[kv_dim_start:kv_dim_end]),
                sk=np.ascontiguousarray(self.sk[kv_dim_start:kv_dim_end]),
                wv=np.ascontiguousarray(self.wv[kv_dim_start:kv_dim_end]),
                sv=np.ascontiguousarray(self.sv[kv_dim_start:kv_dim_end]),
                wo=np.ascontiguousarray(self.wo[:, q_start:q_end]),
                so=np.ascontiguousarray(self.so),
                bq=np.ascontiguousarray(self.bq[q_start:q_end]),
                bk=np.ascontiguousarray(self.bk[kv_dim_start:kv_dim_end]),
                bv=np.ascontiguousarray(self.bv[kv_dim_start:kv_dim_end]),
                checksum="",
                input_ops=list(self.input_ops),
                post_ops=list(self.post_ops) if chunk_index == chunk_count - 1 else [],
                chunk_index=chunk_index,
                chunk_count=chunk_count,
            )
            chunk.checksum = chunk.compute_checksum()
            chunks.append(chunk)
        return chunks


@dataclass
class GQAAttentionChunkLayer(GQAAttentionLayer):
    """A head-group GQA microshard with verified output-sum custody."""

    chunk_index: int = 0
    chunk_count: int = 1

    layer_type = "gqa_attention_chunk"

    @property
    def hidden_size(self) -> int:
        return self.seq * self.d_model

    @property
    def input_size(self) -> int:
        return self.hidden_size if self.chunk_index == 0 else 2 * self.hidden_size

    def source_input(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x, dtype=np.float64).reshape(-1)[: self.hidden_size]

    def custody_output(self, z_flat: np.ndarray, layer_input: np.ndarray) -> np.ndarray:
        from app.ml.model_store import apply_post_ops

        state = np.asarray(layer_input, dtype=np.float64).reshape(-1)
        source = state[: self.hidden_size]
        prior = (
            np.zeros(self.hidden_size, dtype=np.float64)
            if self.chunk_index == 0
            else state[self.hidden_size :]
        )
        accumulated = prior + self.z_output(z_flat)
        if self.chunk_index == self.chunk_count - 1:
            return apply_post_ops(accumulated, self.post_ops, layer_input=source)
        return np.concatenate([source, accumulated])

    def wire_payload(self) -> dict:
        payload = super().wire_payload()
        payload.update(
            {
                "type": "gqa_attention_chunk",
                "chunkIndex": self.chunk_index,
                "chunkCount": self.chunk_count,
                "inputShape": [1, self.input_size],
            }
        )
        return payload


@dataclass
class SwigluMlpLayer:
    """SwiGLU MLP block unit (see module docstring)."""

    index: int
    name: str
    seq: int
    d_model: int
    ffn_dim: int
    wg: np.ndarray  # int8 (ffn, d)
    sg: np.ndarray
    wu: np.ndarray  # int8 (ffn, d)
    su: np.ndarray
    wd: np.ndarray  # int8 (d, ffn)
    sd: np.ndarray
    checksum: str
    input_ops: List[dict] = field(default_factory=list)
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "swiglu_mlp"
    activation = "linear"

    @property
    def input_size(self) -> int:
        return self.seq * self.d_model

    def offsets(self) -> dict:
        t, f, d = self.seq, self.ffn_dim, self.d_model
        return {"G": (0, t * f), "U": (t * f, 2 * t * f), "D": (2 * t * f, 2 * t * f + t * d)}

    @property
    def output_size(self) -> int:
        return self.offsets()["D"][1]

    @property
    def compute_ops(self) -> int:
        return self.seq * self.d_model * self.ffn_dim * 3

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def extract(self, z_flat: np.ndarray) -> dict:
        z = np.asarray(z_flat, dtype=np.float64)
        offs = self.offsets()
        return {
            "G": z[offs["G"][0] : offs["G"][1]].reshape(self.seq, self.ffn_dim),
            "U": z[offs["U"][0] : offs["U"][1]].reshape(self.seq, self.ffn_dim),
            "D": z[offs["D"][0] : offs["D"][1]].reshape(self.seq, self.d_model),
        }

    def z_output(self, z_flat: np.ndarray) -> np.ndarray:
        start, end = self.offsets()["D"]
        return np.asarray(z_flat, dtype=np.float64)[start:end]

    def dequant(self, which: str) -> np.ndarray:
        w, s = {"g": (self.wg, self.sg), "u": (self.wu, self.su), "d": (self.wd, self.sd)}[which]
        return dequantize_rows(w, s)

    def forward(self, x: np.ndarray, pad_len: int = 0) -> np.ndarray:
        from app.ml.model_store import apply_post_ops

        xn = apply_post_ops(x, self.input_ops).reshape(self.seq, self.d_model)
        g = xn @ self.dequant("g").astype(np.float64).T
        u = xn @ self.dequant("u").astype(np.float64).T
        h = silu(g) * u
        d = h @ self.dequant("d").astype(np.float64).T
        return np.concatenate([g.reshape(-1), u.reshape(-1), d.reshape(-1)])

    def wire_payload(self) -> dict:
        import base64

        def b64(arr):
            return base64.b64encode(
                np.ascontiguousarray(arr, dtype="<i1").tobytes()
            ).decode("ascii")

        return {
            "name": self.name,
            "type": "swiglu_mlp",
            "seq": self.seq,
            "dModel": self.d_model,
            "ffnDim": self.ffn_dim,
            "weights": [],
            "biases": [],
            "weightsB64": b64(np.concatenate([w.reshape(-1) for w in (self.wg, self.wu, self.wd)])),
            "scales": np.concatenate([self.sg, self.su, self.sd]).astype(np.float32).tolist(),
            "inputShape": [self.seq, self.d_model],
            "outputShape": [self.output_size],
            "activation": "linear",
            "inputOps": list(self.input_ops),
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        for w in (self.wg, self.wu, self.wd):
            h.update(np.ascontiguousarray(w, dtype="<i1").tobytes())
        for s in (self.sg, self.su, self.sd):
            h.update(np.ascontiguousarray(s, dtype="<f4").tobytes())
        return h.hexdigest()

    def split(self, chunk_count: int) -> List["SwigluMlpChunkLayer"]:
        """Split the FFN axis into independently provable partial sums."""
        if chunk_count < 1 or chunk_count > self.ffn_dim:
            raise ValueError("invalid SwiGLU chunk count")

        chunks: List[SwigluMlpChunkLayer] = []
        boundaries = np.linspace(0, self.ffn_dim, chunk_count + 1, dtype=int)
        for chunk_index, (start, end) in enumerate(
            zip(boundaries[:-1], boundaries[1:])
        ):
            chunk = SwigluMlpChunkLayer(
                index=-1,
                name=f"{self.name}_part{chunk_index + 1}of{chunk_count}",
                seq=self.seq,
                d_model=self.d_model,
                ffn_dim=int(end - start),
                wg=np.ascontiguousarray(self.wg[start:end]),
                sg=np.ascontiguousarray(self.sg[start:end]),
                wu=np.ascontiguousarray(self.wu[start:end]),
                su=np.ascontiguousarray(self.su[start:end]),
                wd=np.ascontiguousarray(self.wd[:, start:end]),
                sd=np.ascontiguousarray(self.sd),
                checksum="",
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                input_ops=list(self.input_ops),
                post_ops=list(self.post_ops) if chunk_index == chunk_count - 1 else [],
            )
            chunk.checksum = chunk.compute_checksum()
            chunks.append(chunk)
        return chunks


@dataclass
class SwigluMlpChunkLayer:
    """
    A vertical SwiGLU microshard with server-custodied partial aggregation.

    Each chunk proves G/U for a disjoint FFN-neuron slice and a partial
    down-projection D. Between browser sessions the pipeline activation is
    ``[original_hidden | accumulated_D]``. Only the final chunk applies the
    original residual/post-op chain, so no client can substitute or omit a
    partial sum.
    """

    index: int
    name: str
    seq: int
    d_model: int
    ffn_dim: int
    wg: np.ndarray
    sg: np.ndarray
    wu: np.ndarray
    su: np.ndarray
    wd: np.ndarray
    sd: np.ndarray
    checksum: str
    chunk_index: int
    chunk_count: int
    input_ops: List[dict] = field(default_factory=list)
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "swiglu_mlp_chunk"
    activation = "linear"

    @property
    def hidden_size(self) -> int:
        return self.seq * self.d_model

    @property
    def input_size(self) -> int:
        return self.hidden_size if self.chunk_index == 0 else 2 * self.hidden_size

    def offsets(self) -> dict:
        t, f, d = self.seq, self.ffn_dim, self.d_model
        return {
            "G": (0, t * f),
            "U": (t * f, 2 * t * f),
            "D": (2 * t * f, 2 * t * f + t * d),
        }

    @property
    def output_size(self) -> int:
        return self.offsets()["D"][1]

    @property
    def compute_ops(self) -> int:
        return self.seq * self.d_model * self.ffn_dim * 3

    @property
    def projection_ops(self) -> int:
        return self.hidden_size + self.output_size

    def source_input(self, x: np.ndarray) -> np.ndarray:
        state = np.asarray(x, dtype=np.float64).reshape(-1)
        return state[: self.hidden_size]

    def transformed_input(self, x: np.ndarray) -> np.ndarray:
        from app.ml.model_store import apply_post_ops

        return apply_post_ops(
            self.source_input(x), self.input_ops
        ).reshape(self.seq, self.d_model)

    def extract(self, z_flat: np.ndarray) -> dict:
        z = np.asarray(z_flat, dtype=np.float64)
        offs = self.offsets()
        return {
            "G": z[offs["G"][0] : offs["G"][1]].reshape(
                self.seq, self.ffn_dim
            ),
            "U": z[offs["U"][0] : offs["U"][1]].reshape(
                self.seq, self.ffn_dim
            ),
            "D": z[offs["D"][0] : offs["D"][1]].reshape(
                self.seq, self.d_model
            ),
        }

    def dequant(self, which: str) -> np.ndarray:
        w, s = {
            "g": (self.wg, self.sg),
            "u": (self.wu, self.su),
            "d": (self.wd, self.sd),
        }[which]
        return dequantize_rows(w, s)

    def forward(self, x: np.ndarray, pad_len: int = 0) -> np.ndarray:
        xn = self.transformed_input(x)
        g = xn @ self.dequant("g").astype(np.float64).T
        u = xn @ self.dequant("u").astype(np.float64).T
        h = silu(g) * u
        d = h @ self.dequant("d").astype(np.float64).T
        return np.concatenate([g.reshape(-1), u.reshape(-1), d.reshape(-1)])

    def custody_output(self, z_flat: np.ndarray, layer_input: np.ndarray) -> np.ndarray:
        """Advance the server-owned partial sum after this proof is valid."""
        from app.ml.model_store import apply_post_ops

        state = np.asarray(layer_input, dtype=np.float64).reshape(-1)
        source = state[: self.hidden_size]
        prior = (
            np.zeros(self.hidden_size, dtype=np.float64)
            if self.chunk_index == 0
            else state[self.hidden_size :]
        )
        partial = self.extract(z_flat)["D"].reshape(-1)
        accumulated = prior + partial
        if self.chunk_index == self.chunk_count - 1:
            return apply_post_ops(accumulated, self.post_ops, layer_input=source)
        return np.concatenate([source, accumulated])

    def wire_payload(self) -> dict:
        import base64

        weights = np.concatenate(
            [self.wg.reshape(-1), self.wu.reshape(-1), self.wd.reshape(-1)]
        )
        scales = np.concatenate([self.sg, self.su, self.sd])
        return {
            "name": self.name,
            "type": "swiglu_mlp_chunk",
            "seq": self.seq,
            "dModel": self.d_model,
            "ffnDim": self.ffn_dim,
            "chunkIndex": self.chunk_index,
            "chunkCount": self.chunk_count,
            "weights": [],
            "biases": [],
            "weightsB64": base64.b64encode(
                np.ascontiguousarray(weights, dtype="<i1").tobytes()
            ).decode("ascii"),
            "scales": scales.astype(np.float32).tolist(),
            "inputShape": [1, self.input_size],
            "outputShape": [self.output_size],
            "activation": "linear",
            "inputOps": list(self.input_ops),
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        for w in (self.wg, self.wu, self.wd):
            h.update(np.ascontiguousarray(w, dtype="<i1").tobytes())
        for s in (self.sg, self.su, self.sd):
            h.update(np.ascontiguousarray(s, dtype="<f4").tobytes())
        return h.hexdigest()


@dataclass
class CandidateLogitsLayer:
    """
    Zero-shot classification head: RMSNorm the LAST token's hidden state and
    project it onto the candidate answer tokens' tied embedding rows. Affine
    in the transformed input — verified by the standard projection check.
    """

    index: int
    name: str
    seq: int
    d_model: int
    weights: np.ndarray  # f32 (n_labels, d) — candidate embedding rows
    checksum: str
    input_ops: List[dict] = field(default_factory=list)  # last_token + rmsnorm
    post_ops: List[dict] = field(default_factory=list)  # softmax

    layer_type = "candidate_logits"
    activation = "softmax"

    @property
    def input_size(self) -> int:
        return self.seq * self.d_model

    @property
    def output_size(self) -> int:
        return self.weights.shape[0]

    @property
    def compute_ops(self) -> int:
        return self.weights.shape[0] * self.d_model

    @property
    def projection_ops(self) -> int:
        return self.d_model + self.output_size

    def transformed_input(self, x: np.ndarray) -> np.ndarray:
        from app.ml.model_store import apply_post_ops

        return apply_post_ops(x, self.input_ops)

    def forward(self, x: np.ndarray, pad_len: int = 0) -> np.ndarray:
        xn = self.transformed_input(x)
        return xn @ self.weights.astype(np.float64).T

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, float]:
        """s = Wᵀr over the TRANSFORMED input (d_model-sized); no bias."""
        return self.weights.astype(np.float64).T @ r, 0.0

    def wire_payload(self) -> dict:
        return {
            "name": self.name,
            "type": "candidate_logits",
            "seq": self.seq,
            "dModel": self.d_model,
            "weights": self.weights.astype(np.float32).flatten().tolist(),
            "biases": [],
            "inputShape": [self.seq, self.d_model],
            "outputShape": [1, self.output_size],
            "activation": "softmax",
            "inputOps": list(self.input_ops),
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights, dtype="<f4").tobytes())
        return h.hexdigest()
