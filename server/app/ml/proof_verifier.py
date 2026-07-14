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
   (attention Q/K/V projections, embeddings-as-matmul). The server holds K
   SECRET random projection vectors r and the precomputed s = Lᵀ·r (computed
   once per model load via layer.project(), never per request). A submitted
   pre-activation z is checked via

       r · z  ≈  s · x  +  r · b

   which costs O(in + out) multiplications instead of the O(in × out) (dense)
   or O(out × k² × in_ch) (conv) the client had to spend. Because r is secret
   and random, a fabricated z that was not actually computed passes K
   independent checks with negligible probability. The layer input x is
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

# Relative tolerance for projection checks. Client computes with float32
# weights/activations in float64 JS arithmetic; the server matches that with
# float64 over the same float32 weights, so honest drift is ~1e-5 relative.
PROJECTION_RTOL = 1e-3

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

    Secret projections are derived deterministically from the server secret
    key + model checksum, so multiple workers agree without sharing state,
    while clients (who never see the secret key) cannot reconstruct them.
    """

    def __init__(self, audit_rate: float = DEFAULT_AUDIT_RATE):
        self.audit_rate = audit_rate
        # (model_checksum, layer_index) -> list of (r, s=W·r, r·b) tuples
        self._projections: Dict[Tuple[str, int], List[Tuple[np.ndarray, np.ndarray, float]]] = {}

    def _layer_projections(
        self, model: ModelSpec, layer_index: int
    ) -> List[Tuple[np.ndarray, np.ndarray, float]]:
        key = (model.checksum, layer_index)
        if key not in self._projections:
            layer = model.layers[layer_index]
            exact = getattr(layer, "exact", False)
            projections = []
            for k in range(NUM_PROJECTIONS):
                seed_material = (
                    f"{settings.secret_key}:{model.checksum}:{layer_index}:{k}"
                ).encode("utf-8")
                seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
                rng = np.random.default_rng(seed)
                if exact:
                    # Quantized layer: secret vector over Z_p for EXACT checks
                    r = rng.integers(1, MOD_P, size=layer.output_size)
                else:
                    r = rng.standard_normal(layer.output_size)
                # s = Lᵀr and r·b, layer-type-specific but verified identically
                s, r_dot_b = layer.project(r)
                projections.append((r, s, r_dot_b))
            self._projections[key] = projections
        return self._projections[key]

    def _attention_projections(self, model: ModelSpec, layer_index: int, layer) -> List[dict]:
        """
        Secret vectors for one attention layer. Per projection round:
          r (seq·d)  — affine checks on Q, K, V (vs input X) and Z (vs O)
          u (seq)    — Freivalds product check S = Q·Kᵀ
          w (d)      — Freivalds product check O = P·V
        The sᵢ = Wᵢᵀ-projections are precomputed once per model version.
        """
        key = (model.checksum, layer_index, "attention")
        if key not in self._projections:
            rounds = []
            for k in range(NUM_PROJECTIONS):
                seed_material = (
                    f"{settings.secret_key}:{model.checksum}:{layer_index}:{k}:attention"
                ).encode("utf-8")
                seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
                rng = np.random.default_rng(seed)
                r = rng.standard_normal(layer.seq * layer.d_model)
                u = rng.standard_normal(layer.seq)
                w = rng.standard_normal(layer.d_model)
                r3 = r.reshape(layer.seq, layer.d_model)
                rounds.append(
                    {
                        "r": r,
                        "u": u,
                        "w": w,
                        "sq": r3 @ layer.wq.astype(np.float64).T,
                        "sk": r3 @ layer.wk.astype(np.float64).T,
                        "sv": r3 @ layer.wv.astype(np.float64).T,
                        "sz": r3 @ layer.wo.astype(np.float64).T,
                    }
                )
            self._projections[key] = rounds
        return self._projections[key]

    @staticmethod
    def _close(lhs: float, rhs: float) -> bool:
        scale = max(1.0, abs(lhs), abs(rhs))
        return abs(lhs - rhs) <= PROJECTION_RTOL * scale

    @staticmethod
    def _vectors_close(lhs: np.ndarray, rhs: np.ndarray) -> bool:
        scale = max(1.0, float(np.max(np.abs(lhs))), float(np.max(np.abs(rhs))))
        return float(np.max(np.abs(lhs - rhs))) <= PROJECTION_RTOL * scale

    def _gqa_projections(self, model: ModelSpec, layer_index: int, layer) -> List[dict]:
        """
        Secret vectors for one GQA attention unit. RoPE is a fixed orthogonal
        per-position rotation, so it folds into the precompute: the affine
        check for the ROTATED Q uses r_eff = Rᵀr (inverse rotation), giving
        r·vec(RoPE(XnW+b)) = Σ_t (Wᵀ r_eff_t)·xn_t + r_eff·b.
        """
        from app.ml.llm_layers import apply_rope, rope_cos_sin

        key = (model.checksum, layer_index, "gqa")
        if key not in self._projections:
            cos, sin = rope_cos_sin(layer.seq, layer.head_dim, layer.rope_theta)
            wq = layer.dequant("q").astype(np.float64)  # (out, in)
            wk = layer.dequant("k").astype(np.float64)
            wv = layer.dequant("v").astype(np.float64)
            wo = layer.dequant("o").astype(np.float64)
            rounds = []
            for k in range(NUM_PROJECTIONS):
                seed_material = (
                    f"{settings.secret_key}:{model.checksum}:{layer_index}:{k}:gqa"
                ).encode("utf-8")
                seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
                rng = np.random.default_rng(seed)
                rq = rng.standard_normal((layer.seq, layer.n_heads, layer.head_dim))
                rk = rng.standard_normal((layer.seq, layer.n_kv_heads, layer.head_dim))
                rv = rng.standard_normal((layer.seq, layer.n_kv_heads, layer.head_dim))
                rz = rng.standard_normal((layer.seq, layer.d_model))
                u = rng.standard_normal(layer.seq)
                w = rng.standard_normal(layer.head_dim)
                rq_eff = apply_rope(rq, cos, -sin).reshape(layer.seq, -1)
                rk_eff = apply_rope(rk, cos, -sin).reshape(layer.seq, -1)
                rv_flat = rv.reshape(layer.seq, -1)
                rounds.append(
                    {
                        "rq": rq.reshape(layer.seq, -1),
                        "rk": rk.reshape(layer.seq, -1),
                        "rv": rv_flat,
                        "rz": rz,
                        "u": u,
                        "w": w,
                        "sq": rq_eff @ wq,  # (seq, d_model)
                        "sk": rk_eff @ wk,
                        "sv": rv_flat @ wv,
                        "sz": rz @ wo,  # (seq, q_dim)
                        "rbq": float(np.sum(rq_eff @ layer.bq.astype(np.float64))),
                        "rbk": float(np.sum(rk_eff @ layer.bk.astype(np.float64))),
                        "rbv": float(np.sum(rv_flat @ layer.bv.astype(np.float64))),
                    }
                )
            self._projections[key] = rounds
        return self._projections[key]

    def _verify_gqa_attention(
        self,
        model: ModelSpec,
        layer_index: int,
        layer,
        x: np.ndarray,
        z: np.ndarray,
        pad_len: int,
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

        for rd in self._gqa_projections(model, layer_index, layer):
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

    def _swiglu_projections(self, model: ModelSpec, layer_index: int, layer) -> List[dict]:
        key = (model.checksum, layer_index, "swiglu")
        if key not in self._projections:
            wg = layer.dequant("g").astype(np.float64)  # (ffn, d)
            wu = layer.dequant("u").astype(np.float64)
            wd = layer.dequant("d").astype(np.float64)  # (d, ffn)
            rounds = []
            for k in range(NUM_PROJECTIONS):
                seed_material = (
                    f"{settings.secret_key}:{model.checksum}:{layer_index}:{k}:swiglu"
                ).encode("utf-8")
                seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
                rng = np.random.default_rng(seed)
                rg = rng.standard_normal((layer.seq, layer.ffn_dim))
                ru = rng.standard_normal((layer.seq, layer.ffn_dim))
                rdv = rng.standard_normal((layer.seq, layer.d_model))
                rounds.append(
                    {
                        "rg": rg,
                        "ru": ru,
                        "rd": rdv,
                        "sg": rg @ wg,  # (seq, d)
                        "su": ru @ wu,
                        "sd": rdv @ wd,  # (seq, ffn)
                    }
                )
            self._projections[key] = rounds
        return self._projections[key]

    def _verify_swiglu(
        self, model: ModelSpec, layer_index: int, layer, x: np.ndarray, z: np.ndarray
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

        for rd in self._swiglu_projections(model, layer_index, layer):
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
        self, model: ModelSpec, layer_index: int, layer, x: np.ndarray, z: np.ndarray
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

        for round_data in self._attention_projections(model, layer_index, layer):
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
                failure = self._verify_attention(model, layer_index, layer, x, z)
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
                    model, layer_index, layer, x, z, pad_len
                )
                if failure:
                    report.reason = failure
                    logger.warning(
                        "GQA check failed: task=%s layer=%d (%s)",
                        task_id, layer_index, failure,
                    )
                    return report
            elif layer.layer_type == "swiglu_mlp":
                failure = self._verify_swiglu(model, layer_index, layer, x, z)
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
                for r, s, rb in self._layer_projections(model, layer_index):
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
                for r, s, rb in self._layer_projections(model, layer_index):
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
