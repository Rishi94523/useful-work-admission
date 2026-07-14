"""
Proof-of-computation verifier.

Verifies that a client really executed its assigned model layers WITHOUT the
server re-running the computation. Three mechanisms, cheapest first:

1. Commitment hashes — the client hashes each submitted pre-activation vector
   and binds them (with task id, sample id and segment position) into a single
   proof hash. The server recomputes these hashes from the submitted data, so
   a proof cannot be replayed for another task or detached from its outputs.

2. Freivalds-style projection checks — the core mechanism. Every provable
   layer is an affine operator (z = L·x + b): dense layers (L = matmul),
   conv2d layers (L = convolution), and by extension any matmul-shaped op
   (attention Q/K/V projections, embeddings-as-matmul). The server holds a
   wider SECRET basis of random projection pairs `(r_j, s_j=Lᵀ·r_j)`, computed
   once per model version via layer.project(). Each assignment HMAC-derives K
   hidden linear combinations from that basis. A submitted pre-activation z
   is checked via

       r · z  ≈  s · x  +  r · b

   which costs O(in + out) multiplications instead of the O(in × out) (dense)
   or O(out × k² × in_ch) (conv) the client had to spend. Because each task's
   equations are secret-derived, a task-tailored fabricated z cannot simply be
   replayed under the next assignment. The layer input x is
   always known to the server: it is either the sample input (segment start
   0) or the activation handed over from the previously verified segment, so
   every layer in a distributed pipeline is verifiable.

3. Probabilistic spot audits — a small fraction of submissions get a full
   recompute of the segment. This bounds the damage of any adaptive attack
   against the projection checks and keeps an honest baseline measurement.

The asymmetry (client does O(in×out) work, server spends O(in+out) to check
it) is what makes this a proof-of-useful-work CAPTCHA: the verification cost
stays flat as models grow.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.config import get_settings
from app.ml.model_store import MOD_P, ModelSpec, dot_mod

logger = logging.getLogger(__name__)
settings = get_settings()

# Number of secret projection vectors per layer. Each adds an independent
# O(in+out) check; 4 already makes undetected fabrication astronomically
# unlikely while keeping verification ~25-100x cheaper than recomputation.
NUM_PROJECTIONS = 4

# Each assignment receives NUM_PROJECTIONS fresh secret linear combinations
# from a wider, model-version-pinned basis. Keeping the expensive transpose
# projection products in this basis preserves cheap O(in+out) verification
# while preventing one task from reusing another task's exact equations.
PROJECTION_BASIS_SIZE = 8

# Relative tolerance for projection checks. Client computes with float32
# weights/activations in float64 JS arithmetic; the server matches that with
# float64 over the same float32 weights, so honest drift is ~1e-5 relative.
PROJECTION_RTOL = 1e-3

# Bilinear product checks use only client-submitted intermediates on both
# sides. Their honest drift is float32 storage/summation noise, far smaller
# than affine projection drift, so a separate elementwise tolerance prevents
# one altered component from hiding behind an unrelated large vector entry.
PRODUCT_RTOL = 1e-7
PRODUCT_ATOL = 2e-2

# Absolute per-element tolerance for full spot audits (float32 storage noise).
AUDIT_ATOL = 1e-3

# Fraction of submissions that get a full recompute in addition to the
# projection checks.
DEFAULT_AUDIT_RATE = 0.08


def canonical_vector_hash(values: Sequence[float]) -> str:
    """
    Hash exact submitted values as canonical little-endian float64 bytes.

    Decimal formatting is not cross-runtime deterministic at rounding ties.
    Normalizing signed zero and hashing IEEE-754 bytes makes Python and the
    browser agree while binding every submitted value exactly.
    """
    canonical = np.asarray(
        [0.0 if float(value) == 0.0 else float(value) for value in values],
        dtype="<f8",
    )
    return hashlib.sha256(canonical.tobytes()).hexdigest()


def compute_proof_hash(
    task_id: str,
    sample_id: str,
    segment_start: int,
    layer_count: int,
    output_hashes: Sequence[str],
    prediction_hash: str,
    verification_nonce: str = "",
) -> str:
    """Combined proof hash binding outputs to this specific task and segment."""
    parts = [
        task_id,
        sample_id,
        str(segment_start),
        str(layer_count),
        *output_hashes,
        prediction_hash or "",
    ]
    if verification_nonce:
        parts.append(verification_nonce)
    proof_data = ":".join(parts)
    return hashlib.sha256(proof_data.encode("utf-8")).hexdigest()


@dataclass
class VerificationReport:
    """Outcome of verifying one submitted segment."""

    valid: bool
    reason: str = "ok"
    audited: bool = False
    checks_run: List[str] = field(default_factory=list)
    # Post-activation of the segment's last layer (float64). This is what the
    # pipeline stores and hands to the next contributor.
    final_activation: Optional[np.ndarray] = None
    # Class probabilities, only when the segment includes the final layer.
    probabilities: Optional[np.ndarray] = None
    predicted_label: Optional[str] = None
    confidence: Optional[float] = None


class ProofVerifier:
    """
    Verifies segment computations for all loaded models.

    A wider projection basis is derived deterministically from the server
    secret key + model checksum, so multiple workers agree without sharing
    state. Each assignment then receives fresh, secret HMAC-derived linear
    combinations of that basis. Clients see the public assignment nonce but
    cannot reconstruct the algebraic challenge without the server secret.
    """

    def __init__(self, audit_rate: float = DEFAULT_AUDIT_RATE):
        self.audit_rate = audit_rate
        # Expensive transpose-projection values are cached for the wider basis.
        # Per-task challenge vectors are cheap combinations and are not cached.
        self._projection_bases: Dict[Tuple[object, ...], list] = {}

    @staticmethod
    def _secret_seed(*parts: object) -> int:
        """Deterministic server-secret PRF seed shared by verifier workers."""
        message = ":".join(str(part) for part in parts).encode("utf-8")
        digest = hmac.new(
            settings.secret_key.encode("utf-8"),
            message,
            hashlib.sha256,
        ).digest()
        return int.from_bytes(digest[:8], "big")

    def _basis_rng(
        self,
        model: ModelSpec,
        layer_index: int,
        kind: str,
        basis_index: int,
    ) -> np.random.Generator:
        seed = self._secret_seed(
            "projection-basis-v1",
            model.checksum,
            layer_index,
            kind,
            basis_index,
        )
        return np.random.default_rng(seed)

    def _challenge_coefficients(
        self,
        model: ModelSpec,
        layer_index: int,
        kind: str,
        assignment_challenge: str,
        *,
        exact: bool = False,
    ) -> np.ndarray:
        """Derive a fresh hidden coefficient matrix for one assignment."""
        seed = self._secret_seed(
            "projection-challenge-v1",
            model.checksum,
            layer_index,
            kind,
            assignment_challenge,
        )
        rng = np.random.default_rng(seed)

        if exact:
            # Distinct non-zero field elements form a full-row-rank
            # Vandermonde challenge matrix.
            alphas: list[int] = []
            while len(alphas) < NUM_PROJECTIONS:
                alpha = int(rng.integers(1, MOD_P))
                if alpha not in alphas:
                    alphas.append(alpha)
            return np.asarray(
                [
                    [
                        pow(alpha, exponent, MOD_P)
                        for exponent in range(PROJECTION_BASIS_SIZE)
                    ]
                    for alpha in alphas
                ],
                dtype=np.int64,
            )

        # Deterministic Gram-Schmidt gives independent, unit-length rows
        # without relying on a platform-specific QR sign convention.
        raw = rng.standard_normal((NUM_PROJECTIONS, PROJECTION_BASIS_SIZE))
        rows: list[np.ndarray] = []
        for candidate in raw:
            row = candidate.astype(np.float64, copy=True)
            for previous in rows:
                row -= float(row @ previous) * previous
            norm = float(np.linalg.norm(row))
            if norm < 1e-12:
                raise RuntimeError("degenerate projection challenge")
            rows.append(row / norm)
        return np.stack(rows)

    @staticmethod
    def _combine_float_dict_basis(
        basis: Sequence[dict], coefficients: np.ndarray
    ) -> List[dict]:
        """Linearly combine dict-shaped float projection basis records."""
        combined_rounds: List[dict] = []
        for row in coefficients:
            combined: dict = {}
            for name in basis[0]:
                first = basis[0][name]
                if np.isscalar(first):
                    combined[name] = float(
                        sum(
                            float(coefficient) * float(item[name])
                            for coefficient, item in zip(row, basis)
                        )
                    )
                else:
                    acc = np.zeros_like(np.asarray(first), dtype=np.float64)
                    for coefficient, item in zip(row, basis):
                        acc += float(coefficient) * np.asarray(
                            item[name], dtype=np.float64
                        )
                    combined[name] = acc
            combined_rounds.append(combined)
        return combined_rounds

    def _layer_projections(
        self,
        model: ModelSpec,
        layer_index: int,
        assignment_challenge: str,
    ) -> List[Tuple[np.ndarray, np.ndarray, float]]:
        key = (model.checksum, layer_index, "affine-basis")
        if key not in self._projection_bases:
            layer = model.layers[layer_index]
            exact = getattr(layer, "exact", False)
            projections = []
            for basis_index in range(PROJECTION_BASIS_SIZE):
                rng = self._basis_rng(model, layer_index, "affine", basis_index)
                if exact:
                    r = rng.integers(
                        1,
                        MOD_P,
                        size=layer.output_size,
                        dtype=np.int64,
                    )
                else:
                    # Basis records are stored as float32 to offset the wider
                    # pool's memory cost; combinations/checks use float64.
                    r = rng.standard_normal(layer.output_size).astype(np.float32)
                s, r_dot_b = layer.project(r)
                if not exact:
                    s = np.asarray(s, dtype=np.float32)
                projections.append((r, s, r_dot_b))
            self._projection_bases[key] = projections

        basis = self._projection_bases[key]
        exact = getattr(model.layers[layer_index], "exact", False)
        coefficients = self._challenge_coefficients(
            model,
            layer_index,
            "affine",
            assignment_challenge,
            exact=exact,
        )
        rounds: List[Tuple[np.ndarray, np.ndarray, float]] = []

        if exact:
            for row in coefficients:
                r = np.zeros_like(basis[0][0], dtype=np.int64)
                s = np.zeros_like(basis[0][1], dtype=np.int64)
                rb = 0
                for coefficient, (base_r, base_s, base_rb) in zip(row, basis):
                    c = int(coefficient)
                    r = (r + c * np.asarray(base_r, dtype=np.int64)) % MOD_P
                    s = (s + c * np.asarray(base_s, dtype=np.int64)) % MOD_P
                    rb = (rb + c * int(base_rb)) % MOD_P
                rounds.append((r, s, rb))
            return rounds

        for row in coefficients:
            r = np.zeros_like(np.asarray(basis[0][0]), dtype=np.float64)
            s = np.zeros_like(np.asarray(basis[0][1]), dtype=np.float64)
            rb = 0.0
            for coefficient, (base_r, base_s, base_rb) in zip(row, basis):
                c = float(coefficient)
                r += c * np.asarray(base_r, dtype=np.float64)
                s += c * np.asarray(base_s, dtype=np.float64)
                rb += c * float(base_rb)
            rounds.append((r, s, rb))
        return rounds

    def _attention_projections(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        assignment_challenge: str,
    ) -> List[dict]:
        """
        Secret vectors for one attention layer. Per projection round:
          r (seq·d)  — affine checks on Q, K, V (vs input X) and Z (vs O)
          u (seq)    — Freivalds product check S = Q·Kᵀ
          w (d)      — Freivalds product check O = P·V
        The sᵢ = Wᵢᵀ-projections are precomputed once per model version.
        """
        key = (model.checksum, layer_index, "attention-basis")
        if key not in self._projection_bases:
            rounds = []
            for basis_index in range(PROJECTION_BASIS_SIZE):
                rng = self._basis_rng(
                    model, layer_index, "attention", basis_index
                )
                r = rng.standard_normal(layer.seq * layer.d_model).astype(np.float32)
                r3 = r.astype(np.float64).reshape(layer.seq, layer.d_model)
                rounds.append(
                    {
                        "r": r,
                        "sq": (r3 @ layer.wq.astype(np.float64).T).astype(np.float32),
                        "sk": (r3 @ layer.wk.astype(np.float64).T).astype(np.float32),
                        "sv": (r3 @ layer.wv.astype(np.float64).T).astype(np.float32),
                        "sz": (r3 @ layer.wo.astype(np.float64).T).astype(np.float32),
                    }
                )
            self._projection_bases[key] = rounds
        coefficients = self._challenge_coefficients(
            model, layer_index, "attention", assignment_challenge
        )
        challenged = self._combine_float_dict_basis(
            self._projection_bases[key], coefficients
        )
        for round_index, round_data in enumerate(challenged):
            product_rng = np.random.default_rng(
                self._secret_seed(
                    "product-challenge-v1",
                    model.checksum,
                    layer_index,
                    "attention",
                    assignment_challenge,
                    round_index,
                )
            )
            # These product vectors need no weight projection and can therefore
            # be genuinely fresh rather than combined from the cached basis.
            round_data["u"] = product_rng.standard_normal(layer.seq)
            round_data["w"] = product_rng.standard_normal(layer.d_model)
        return challenged

    @staticmethod
    def _close(lhs: float, rhs: float) -> bool:
        scale = max(1.0, abs(lhs), abs(rhs))
        return abs(lhs - rhs) <= PROJECTION_RTOL * scale

    @staticmethod
    def _vectors_close(lhs: np.ndarray, rhs: np.ndarray) -> bool:
        lhs_values = np.asarray(lhs, dtype=np.float64)
        rhs_values = np.asarray(rhs, dtype=np.float64)
        scale = np.maximum(np.abs(lhs_values), np.abs(rhs_values))
        tolerance = PRODUCT_ATOL + PRODUCT_RTOL * scale
        return bool(np.all(np.abs(lhs_values - rhs_values) <= tolerance))

    def _gqa_projections(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        assignment_challenge: str,
    ) -> List[dict]:
        """
        Secret vectors for one GQA attention unit. RoPE is a fixed orthogonal
        per-position rotation, so it folds into the precompute: the affine
        check for the ROTATED Q uses r_eff = Rᵀr (inverse rotation), giving
        r·vec(RoPE(XnW+b)) = Σ_t (Wᵀ r_eff_t)·xn_t + r_eff·b.
        """
        from app.ml.llm_layers import apply_rope, rope_cos_sin

        key = (model.checksum, layer_index, "gqa-basis")
        if key not in self._projection_bases:
            cos, sin = rope_cos_sin(layer.seq, layer.head_dim, layer.rope_theta)
            wq = layer.dequant("q").astype(np.float64)  # (out, in)
            wk = layer.dequant("k").astype(np.float64)
            wv = layer.dequant("v").astype(np.float64)
            wo = layer.dequant("o").astype(np.float64)
            rounds = []
            for basis_index in range(PROJECTION_BASIS_SIZE):
                rng = self._basis_rng(model, layer_index, "gqa", basis_index)
                rq = rng.standard_normal(
                    (layer.seq, layer.n_heads, layer.head_dim)
                ).astype(np.float32)
                rk = rng.standard_normal(
                    (layer.seq, layer.n_kv_heads, layer.head_dim)
                ).astype(np.float32)
                rv = rng.standard_normal(
                    (layer.seq, layer.n_kv_heads, layer.head_dim)
                ).astype(np.float32)
                rz = rng.standard_normal((layer.seq, layer.d_model)).astype(np.float32)
                rq_eff = apply_rope(
                    rq.astype(np.float64), cos, -sin
                ).reshape(layer.seq, -1)
                rk_eff = apply_rope(
                    rk.astype(np.float64), cos, -sin
                ).reshape(layer.seq, -1)
                rv_flat = rv.astype(np.float64).reshape(layer.seq, -1)
                rounds.append(
                    {
                        "rq": rq.reshape(layer.seq, -1),
                        "rk": rk.reshape(layer.seq, -1),
                        "rv": rv_flat,
                        "rz": rz,
                        "sq": (rq_eff @ wq).astype(np.float32),  # (seq, d_model)
                        "sk": (rk_eff @ wk).astype(np.float32),
                        "sv": (rv_flat @ wv).astype(np.float32),
                        "sz": (rz.astype(np.float64) @ wo).astype(np.float32),
                        "rbq": float(np.sum(rq_eff @ layer.bq.astype(np.float64))),
                        "rbk": float(np.sum(rk_eff @ layer.bk.astype(np.float64))),
                        "rbv": float(np.sum(rv_flat @ layer.bv.astype(np.float64))),
                    }
                )
            self._projection_bases[key] = rounds
        coefficients = self._challenge_coefficients(
            model, layer_index, "gqa", assignment_challenge
        )
        challenged = self._combine_float_dict_basis(
            self._projection_bases[key], coefficients
        )
        for round_index, round_data in enumerate(challenged):
            product_rng = np.random.default_rng(
                self._secret_seed(
                    "product-challenge-v1",
                    model.checksum,
                    layer_index,
                    "gqa",
                    assignment_challenge,
                    round_index,
                )
            )
            round_data["u"] = product_rng.standard_normal(layer.seq)
            round_data["w"] = product_rng.standard_normal(layer.head_dim)
        return challenged

    def _verify_gqa_attention(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        x: np.ndarray,
        z: np.ndarray,
        pad_len: int,
        assignment_challenge: str,
    ) -> Optional[str]:
        """
        Verify a GQA attention submission [Q|K|V|S|O|Z]: affine checks for the
        RoPE'd Q/K and V/Z, per-head Freivalds product checks for S = Q·Kᵀ and
        O = P·V with the masked softmax P computed by the SERVER.
        """
        from app.ml.llm_layers import attention_probs
        from app.ml.model_store import apply_post_ops

        parts = layer.extract(z)
        xn = apply_post_ops(x, layer.input_ops).reshape(layer.seq, layer.d_model)
        p_matrix = attention_probs(parts["S"], layer.head_dim, pad_len)
        hd = layer.head_dim

        for rd in self._gqa_projections(
            model, layer_index, layer, assignment_challenge
        ):
            checks = (
                ("Q", parts["Q"].reshape(layer.seq, -1), rd["rq"], rd["sq"], rd["rbq"]),
                ("K", parts["K"].reshape(layer.seq, -1), rd["rk"], rd["sk"], rd["rbk"]),
                ("V", parts["V"].reshape(layer.seq, -1), rd["rv"], rd["sv"], rd["rbv"]),
            )
            for name, sub, r, s, rb in checks:
                lhs = float(np.sum(r * sub))
                rhs = float(np.sum(s * xn)) + rb
                if not self._close(lhs, rhs):
                    return f"gqa {name} projection failed at layer {layer_index}"

            lhs = float(np.sum(rd["rz"] * parts["Z"]))
            rhs = float(np.sum(rd["sz"] * parts["O"]))
            if not self._close(lhs, rhs):
                return f"gqa Z projection failed at layer {layer_index}"

            u, w = rd["u"], rd["w"]
            for h in range(layer.n_heads):
                g = layer.kv_group(h)
                q_h = parts["Q"][:, h, :]
                k_g = parts["K"][:, g, :]
                v_g = parts["V"][:, g, :]
                if not self._vectors_close(parts["S"][h] @ u, q_h @ (k_g.T @ u)):
                    return f"gqa score product failed at layer {layer_index} head {h}"
                o_h = parts["O"][:, h * hd : (h + 1) * hd]
                if not self._vectors_close(o_h @ w, p_matrix[h] @ (v_g @ w)):
                    return f"gqa output product failed at layer {layer_index} head {h}"

        return None

    def _swiglu_projections(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        assignment_challenge: str,
    ) -> List[dict]:
        key = (model.checksum, layer_index, "swiglu-basis")
        if key not in self._projection_bases:
            wg = layer.dequant("g").astype(np.float64)  # (ffn, d)
            wu = layer.dequant("u").astype(np.float64)
            wd = layer.dequant("d").astype(np.float64)  # (d, ffn)
            rounds = []
            for basis_index in range(PROJECTION_BASIS_SIZE):
                rng = self._basis_rng(model, layer_index, "swiglu", basis_index)
                rg = rng.standard_normal((layer.seq, layer.ffn_dim)).astype(np.float32)
                ru = rng.standard_normal((layer.seq, layer.ffn_dim)).astype(np.float32)
                rdv = rng.standard_normal((layer.seq, layer.d_model)).astype(np.float32)
                rounds.append(
                    {
                        "rg": rg,
                        "ru": ru,
                        "rd": rdv,
                        "sg": (rg.astype(np.float64) @ wg).astype(np.float32),
                        "su": (ru.astype(np.float64) @ wu).astype(np.float32),
                        "sd": (rdv.astype(np.float64) @ wd).astype(np.float32),
                    }
                )
            self._projection_bases[key] = rounds
        coefficients = self._challenge_coefficients(
            model, layer_index, "swiglu", assignment_challenge
        )
        return self._combine_float_dict_basis(
            self._projection_bases[key], coefficients
        )

    def _verify_swiglu(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        x: np.ndarray,
        z: np.ndarray,
        assignment_challenge: str,
    ) -> Optional[str]:
        """
        Verify a SwiGLU MLP submission [G|U|D]: G and U affine in the normed
        input; H = silu(G)⊙U computed by the SERVER from the verified G, U
        (O(ffn) elementwise); D affine in that server-computed H.
        """
        from app.ml.llm_layers import silu
        from app.ml.model_store import apply_post_ops

        parts = layer.extract(z)
        xn = apply_post_ops(x, layer.input_ops).reshape(layer.seq, layer.d_model)
        h_matrix = silu(parts["G"]) * parts["U"]

        for rd in self._swiglu_projections(
            model, layer_index, layer, assignment_challenge
        ):
            for name, sub, r, s in (
                ("G", parts["G"], rd["rg"], rd["sg"]),
                ("U", parts["U"], rd["ru"], rd["su"]),
            ):
                lhs = float(np.sum(r * sub))
                rhs = float(np.sum(s * xn))
                if not self._close(lhs, rhs):
                    return f"swiglu {name} projection failed at layer {layer_index}"

            lhs = float(np.sum(rd["rd"] * parts["D"]))
            rhs = float(np.sum(rd["sd"] * h_matrix))
            if not self._close(lhs, rhs):
                return f"swiglu D projection failed at layer {layer_index}"

        return None

    def _verify_attention(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        x: np.ndarray,
        z: np.ndarray,
        assignment_challenge: str,
    ) -> Optional[str]:
        """
        Verify a submitted attention concatenation [Q|K|V|S|O|Z] without
        recomputing the block:
          1. Q, K, V affine in the known input X (secret projections).
          2. S = Q·Kᵀ via Freivalds on the submitted (now-verified) Q, K.
          3. P = softmax(S) computed by the SERVER (cheap, O(seq²)).
          4. O = P·V via Freivalds.
          5. Z = O·Wo affine in the verified O.
        Returns a failure reason, or None if all checks pass.
        """
        parts = layer.extract(z)
        xt = np.asarray(x, dtype=np.float64).reshape(layer.seq, layer.d_model)
        p_matrix = layer.softmax_rows(parts["S"])

        for round_data in self._attention_projections(
            model, layer_index, layer, assignment_challenge
        ):
            r = round_data["r"]
            # 1. Affine checks: r·vec(M) == Σ_t s[t]·X[t]
            for name, s in (("Q", "sq"), ("K", "sk"), ("V", "sv")):
                lhs = float(r @ parts[name].reshape(-1))
                rhs = float(np.sum(round_data[s] * xt))
                if not self._close(lhs, rhs):
                    return f"attention {name} projection failed at layer {layer_index}"

            # 5. Z affine in the submitted O
            lhs = float(r @ parts["Z"].reshape(-1))
            rhs = float(np.sum(round_data["sz"] * parts["O"]))
            if not self._close(lhs, rhs):
                return f"attention Z projection failed at layer {layer_index}"

            # 2. S = Q·Kᵀ (Freivalds matrix-product check)
            u = round_data["u"]
            if not self._vectors_close(parts["S"] @ u, parts["Q"] @ (parts["K"].T @ u)):
                return f"attention score product check failed at layer {layer_index}"

            # 4. O = softmax(S)·V with server-computed softmax
            w = round_data["w"]
            if not self._vectors_close(parts["O"] @ w, p_matrix @ (parts["V"] @ w)):
                return f"attention output product check failed at layer {layer_index}"

        return None

    def verify_segment(
        self,
        model: ModelSpec,
        segment_start: int,
        input_vector: Sequence[float],
        pre_activations: List[List[float]],
        output_hashes: List[str],
        proof_hash: str,
        task_id: str,
        sample_id: str,
        prediction_hash: str = "",
        force_audit: bool = False,
        context: Optional[dict] = None,
        verification_nonce: str = "",
    ) -> VerificationReport:
        """Verify one submitted segment of layers [start, start+len)."""
        pad_len = int((context or {}).get("pad_len", 0))
        layer_count = len(pre_activations)
        segment_end = segment_start + layer_count
        report = VerificationReport(valid=False)
        # Production tasks provide a random nonce. The task id fallback keeps
        # internal/offline callers assignment-specific as well.
        assignment_challenge = (
            f"{task_id}:{verification_nonce}" if verification_nonce else task_id
        )

        # --- Structural checks -------------------------------------------
        if segment_end > model.total_layers:
            report.reason = "segment exceeds model depth"
            return report
        if len(output_hashes) != layer_count:
            report.reason = "output hash count mismatch"
            return report
        for offset, z in enumerate(pre_activations):
            expected = model.layers[segment_start + offset].output_size
            if len(z) != expected:
                report.reason = (
                    f"layer {segment_start + offset} output size "
                    f"{len(z)} != {expected}"
                )
                return report
        report.checks_run.append("structure")

        # --- Commitment hashes --------------------------------------------
        for offset, z in enumerate(pre_activations):
            if canonical_vector_hash(z) != output_hashes[offset]:
                report.reason = f"commitment hash mismatch at layer {segment_start + offset}"
                return report
        expected_proof = compute_proof_hash(
            task_id,
            sample_id,
            segment_start,
            layer_count,
            output_hashes,
            prediction_hash,
            verification_nonce,
        )
        if proof_hash != expected_proof:
            report.reason = "proof hash mismatch"
            return report
        report.checks_run.append("commitments")

        # --- Freivalds projection checks ----------------------------------
        x = np.asarray(input_vector, dtype=np.float64)
        for offset, z_submitted in enumerate(pre_activations):
            layer_index = segment_start + offset
            layer = model.layers[layer_index]
            if len(x) != layer.input_size:
                report.reason = f"input size mismatch at layer {layer_index}"
                return report

            z = np.asarray(z_submitted, dtype=np.float64)
            if layer.layer_type == "attention":
                failure = self._verify_attention(
                    model,
                    layer_index,
                    layer,
                    x,
                    z,
                    assignment_challenge,
                )
                if failure:
                    report.reason = failure
                    logger.warning(
                        "Attention check failed: task=%s layer=%d (%s)",
                        task_id,
                        layer_index,
                        failure,
                    )
                    return report
            elif layer.layer_type == "gqa_attention":
                failure = self._verify_gqa_attention(
                    model,
                    layer_index,
                    layer,
                    x,
                    z,
                    pad_len,
                    assignment_challenge,
                )
                if failure:
                    report.reason = failure
                    logger.warning(
                        "GQA check failed: task=%s layer=%d (%s)",
                        task_id, layer_index, failure,
                    )
                    return report
            elif layer.layer_type == "swiglu_mlp":
                failure = self._verify_swiglu(
                    model,
                    layer_index,
                    layer,
                    x,
                    z,
                    assignment_challenge,
                )
                if failure:
                    report.reason = failure
                    logger.warning(
                        "SwiGLU check failed: task=%s layer=%d (%s)",
                        task_id, layer_index, failure,
                    )
                    return report
            elif getattr(layer, "exact", False):
                # EXACT mod-p verification (quantized layers): every honest
                # value is an integer, so equality is bit-for-bit — no float
                # tolerance for a cheater to hide inside.
                if not np.all(z == np.floor(z)) or np.any(np.abs(z) >= 2**53):
                    report.reason = (
                        f"non-integer output for quantized layer {layer_index}"
                    )
                    return report
                z_int = [int(v) for v in z]
                x_int = [int(v) for v in x]
                for r, s, rb in self._layer_projections(
                    model, layer_index, assignment_challenge
                ):
                    lhs = dot_mod(r, z_int)
                    rhs = (dot_mod(s, x_int) + rb) % MOD_P
                    if lhs != rhs:
                        report.reason = (
                            f"exact projection check failed at layer {layer_index}"
                        )
                        logger.warning(
                            "Exact projection failed: task=%s layer=%d",
                            task_id,
                            layer_index,
                        )
                        return report
            else:
                # layers with input-ops (e.g. candidate_logits: last_token +
                # rmsnorm) are affine in the TRANSFORMED input, which the
                # server derives itself in O(n)
                x_eff = (
                    layer.transformed_input(x)
                    if hasattr(layer, "transformed_input")
                    else x
                )
                for r, s, rb in self._layer_projections(
                    model, layer_index, assignment_challenge
                ):
                    lhs = float(r @ z)
                    rhs = float(s @ x_eff) + rb
                    scale = max(1.0, abs(lhs), abs(rhs))
                    if abs(lhs - rhs) > PROJECTION_RTOL * scale:
                        report.reason = (
                            f"projection check failed at layer {layer_index} "
                            f"(|{lhs:.6f} - {rhs:.6f}| > {PROJECTION_RTOL * scale:.6f})"
                        )
                        logger.warning(
                            "Projection check failed: task=%s layer=%d",
                            task_id,
                            layer_index,
                        )
                        return report

            # Server applies the (cheap) post-ops itself — activation,
            # pooling, flatten, residual, token pooling; the result feeds the
            # next layer's check and is what the pipeline stores.
            x = model.apply_layer_post_ops(z, layer_index, layer_input=x)
        report.checks_run.append("projections")

        # --- Probabilistic spot audit --------------------------------------
        # Quantized segments are verified EXACTLY above — audits add nothing.
        all_exact = all(
            getattr(model.layers[segment_start + o], "exact", False)
            for o in range(layer_count)
        )
        if not all_exact and (force_audit or random.random() < self.audit_rate):
            expected_pre, _ = model.forward_segment(
                np.asarray(input_vector, dtype=np.float64),
                segment_start,
                segment_end,
                pad_len=pad_len,
            )
            for offset, z_submitted in enumerate(pre_activations):
                diff = np.max(
                    np.abs(np.asarray(z_submitted, dtype=np.float64) - expected_pre[offset])
                )
                if diff > AUDIT_ATOL:
                    report.audited = True
                    report.reason = (
                        f"spot audit failed at layer {segment_start + offset} "
                        f"(max diff {diff:.6f})"
                    )
                    logger.warning("Spot audit failed: task=%s", task_id)
                    return report
            report.audited = True
            report.checks_run.append("audit")

        # --- Success: derive outputs ---------------------------------------
        report.valid = True
        report.final_activation = x
        if segment_end == model.total_layers:
            # x is already the softmax output of the final layer
            report.probabilities = x
            top = int(np.argmax(x))
            report.predicted_label = model.labels[top]
            report.confidence = float(x[top])
        return report


_verifier: Optional[ProofVerifier] = None


def get_proof_verifier() -> ProofVerifier:
    """Get or create the global proof verifier."""
    global _verifier
    if _verifier is None:
        audit_rate = getattr(settings, "proof_audit_rate", DEFAULT_AUDIT_RATE)
        _verifier = ProofVerifier(audit_rate=audit_rate)
    return _verifier


def reset_proof_verifier() -> None:
    """Reset the global verifier (for tests)."""
    global _verifier
    _verifier = None
