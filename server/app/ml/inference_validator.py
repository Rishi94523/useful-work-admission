"""Inference validator: verifies submitted segment proofs without recomputation."""

import hashlib
import logging
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.config import get_settings
from app.models import Task, Session, Prediction, Verification
from app.schemas import PredictionData, TimingData, InferenceProofData
from app.ml.model_store import get_model_store
from app.ml.proof_verifier import VerificationReport, get_proof_verifier

logger = logging.getLogger(__name__)
settings = get_settings()


def hash_prediction(prediction: PredictionData) -> str:
    """
    Canonical prediction hash; mirrored by the browser client. Uses explicit
    fixed-point formatting (not JSON) so float serialization is identical in
    JS (toFixed(4)) and Python (:.4f).
    """
    top_k = ",".join(
        f"{item.label}:{item.confidence:.4f}" for item in prediction.top_k
    )
    payload = "|".join([prediction.label, f"{prediction.confidence:.4f}", top_k])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class InferenceValidator:
    """
    Validates client submissions for shard-inference tasks.

    The heavy lifting happens in ProofVerifier (secret projection checks,
    commitment hashes, spot audits). This class adapts task/session context
    around it: timing plausibility, prediction consistency, and the
    verification-needed decision.
    """

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis

    async def validate_submission(
        self,
        task: Task,
        proof: Optional[InferenceProofData],
        prediction: Optional[PredictionData],
        timing: TimingData,
    ) -> VerificationReport:
        """
        Validate a segment submission. Returns the verifier report; the
        report's final_activation/prediction fields drive the pipeline.
        """
        report = VerificationReport(valid=False)

        if proof is None:
            report.reason = "missing inference proof"
            return report

        if not self._validate_timing(task, timing):
            report.reason = "implausible timing"
            return report

        shard_meta = (task.metadata_ or {}).get("shard_task", {})
        model_name = shard_meta.get("model_name")
        sample_id = shard_meta.get("sample_id")
        segment_start = shard_meta.get("segment_start", 0)
        expected_layers = shard_meta.get("expected_layers", 0)
        input_vector = shard_meta.get("input_vector")
        verification_nonce = shard_meta.get("verification_nonce")

        if not model_name or input_vector is None:
            report.reason = "task missing shard metadata"
            return report
        if not verification_nonce:
            report.reason = "task missing verification challenge"
            return report

        model = get_model_store().get(model_name)
        if model is None:
            report.reason = f"unknown model {model_name}"
            return report

        if shard_meta.get("model_checksum") != model.checksum:
            # Model was retrained/rotated between assignment and submission.
            report.reason = "model version rotated; please retry"
            return report

        # Bind the proof to the exact task it was issued for
        if proof.task_id != str(task.id):
            report.reason = "proof task mismatch"
            return report
        if proof.sample_id != sample_id:
            report.reason = "proof sample mismatch"
            return report
        if proof.segment_start != segment_start:
            report.reason = "proof segment mismatch"
            return report
        if proof.layer_count != expected_layers:
            report.reason = "proof layer count mismatch"
            return report

        # Prediction must be present exactly on final segments
        is_final_segment = segment_start + expected_layers >= model.total_layers
        prediction_hash = ""
        if is_final_segment:
            if prediction is None:
                report.reason = "final segment requires a prediction"
                return report
            if not self._validate_prediction_plausibility(prediction):
                report.reason = "implausible prediction"
                return report
            prediction_hash = hash_prediction(prediction)
            if proof.prediction_hash != prediction_hash:
                report.reason = "prediction hash mismatch"
                return report

        verifier = get_proof_verifier()
        report = verifier.verify_segment(
            model=model,
            segment_start=segment_start,
            input_vector=input_vector,
            pre_activations=proof.pre_activations,
            output_hashes=proof.output_hashes,
            proof_hash=proof.proof_hash,
            task_id=proof.task_id,
            sample_id=proof.sample_id,
            prediction_hash=prediction_hash,
            context=shard_meta.get("context") or {},
            verification_nonce=verification_nonce,
        )

        if not report.valid:
            logger.warning(
                "Submission rejected for task %s: %s", task.id, report.reason
            )
            return report

        # Server-derived label is authoritative; client's must agree
        if is_final_segment and prediction is not None:
            if report.predicted_label != prediction.label:
                report.valid = False
                report.reason = (
                    f"client label '{prediction.label}' disagrees with "
                    f"server-derived '{report.predicted_label}'"
                )
                return report

        return report

    def _validate_timing(self, task: Task, timing: TimingData) -> bool:
        """Reject submissions faster than physically plausible."""
        expected_ms = task.expected_time_ms
        min_time = expected_ms * 0.1

        if timing.inference_ms < min_time:
            logger.warning(
                "Suspiciously fast inference: %dms < %.0fms",
                timing.inference_ms,
                min_time,
            )
            return False
        return True

    def _validate_prediction_plausibility(self, prediction: PredictionData) -> bool:
        """Confidence bounds and top-k consistency."""
        if not 0 <= prediction.confidence <= 1:
            return False
        if not prediction.top_k:
            return False
        if prediction.top_k[0].label != prediction.label:
            return False
        return True

    async def should_require_verification(
        self,
        session: Session,
        prediction: Prediction,
        *,
        is_known_sample: bool = False,
        base_rate: Optional[float] = None,
    ) -> bool:
        """
        Decide whether to ask this human to verify the completed run's label.

        Only called when a pipeline run completes. Verified labels accumulate
        toward golden-dataset consensus and eventually retraining.
        """
        # Do not let one anonymous browser identity accumulate multiple votes
        # for the same sample. This is best-effort Sybil resistance; a
        # production deployment still needs stronger abuse controls.
        if session.client_fingerprint:
            existing = await self.db.execute(
                select(Verification.id)
                .join(Session, Verification.session_id == Session.id)
                .where(
                    Verification.sample_id == prediction.sample_id,
                    Session.client_fingerprint == session.client_fingerprint,
                )
                .limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                return False

        probability = self.verification_probability(
            session=session,
            prediction=prediction,
            is_known_sample=is_known_sample,
            base_rate=base_rate,
        )
        return random.random() < probability

    @staticmethod
    def verification_probability(
        *,
        session: Session,
        prediction: Prediction,
        is_known_sample: bool = False,
        base_rate: Optional[float] = None,
    ) -> float:
        """Return the human-audit probability for a completed label."""
        if is_known_sample or session.difficulty_tier == "bot_like":
            return 1.0

        configured_rate = (
            settings.verification_rate if base_rate is None else float(base_rate)
        )
        configured_rate = max(0.0, min(1.0, configured_rate))
        tier_rate = 0.5 if session.difficulty_tier == "suspicious" else configured_rate

        threshold = settings.verification_confidence_threshold
        confidence = max(0.0, min(1.0, float(prediction.confidence)))
        if threshold > 0 and confidence < threshold:
            uncertainty = (threshold - confidence) / threshold
            uncertainty_rate = 0.5 + 0.5 * uncertainty
            return min(1.0, max(tier_rate, uncertainty_rate))
        return tier_rate
