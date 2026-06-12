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
from app.ml.model_store import ModelSpec

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
    Hash of a vector in canonical form: values formatted to 4 decimal places,
    comma-joined. Mirrored exactly by the browser client (toFixed(4)).
    """
    canonical = ",".join(f"{float(v):.4f}" for v in values)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_proof_hash(
    task_id: str,
    sample_id: str,
    segment_start: int,
    layer_count: int,
    output_hashes: Sequence[str],
    prediction_hash: str,
) -> str:
    """Combined proof hash binding outputs to this specific task and segment."""
    proof_data = ":".join(
        [
            task_id,
            sample_id,
            str(segment_start),
            str(layer_count),
            *output_hashes,
            prediction_hash or "",
        ]
    )
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
            projections = []
            for k in range(NUM_PROJECTIONS):
                seed_material = (
                    f"{settings.secret_key}:{model.checksum}:{layer_index}:{k}"
                ).encode("utf-8")
                seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
                rng = np.random.default_rng(seed)
                r = rng.standard_normal(layer.output_size)
                # s = Lᵀr and r·b, layer-type-specific but verified identically
                s, r_dot_b = layer.project(r)
                projections.append((r, s, r_dot_b))
            self._projections[key] = projections
        return self._projections[key]

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
    ) -> VerificationReport:
        """Verify one submitted segment of layers [start, start+len)."""
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
            task_id, sample_id, segment_start, layer_count, output_hashes, prediction_hash
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
            for r, s, rb in self._layer_projections(model, layer_index):
                lhs = float(r @ z)
                rhs = float(s @ x) + rb
                scale = max(1.0, abs(lhs), abs(rhs))
                if abs(lhs - rhs) > PROJECTION_RTOL * scale:
                    report.reason = (
                        f"projection check failed at layer {layer_index} "
                        f"(|{lhs:.6f} - {rhs:.6f}| > {PROJECTION_RTOL * scale:.6f})"
                    )
                    logger.warning(
                        "Projection check failed: task=%s layer=%d", task_id, layer_index
                    )
                    return report

            # Server applies the (cheap) post-ops itself — activation,
            # pooling, flatten; the result feeds the next layer's check and
            # is what the pipeline stores.
            x = model.apply_layer_post_ops(z, layer_index)
        report.checks_run.append("projections")

        # --- Probabilistic spot audit --------------------------------------
        if force_audit or random.random() < self.audit_rate:
            expected_pre, _ = model.forward_segment(
                np.asarray(input_vector, dtype=np.float64), segment_start, segment_end
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
