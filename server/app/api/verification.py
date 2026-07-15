"""
Verification API endpoints.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models import get_db, Session, Prediction, Verification, Task, Sample
from app.schemas import VerificationSubmitRequest, VerificationSubmitResponse
from app.services.golden_dataset import GoldenDatasetService
from app.services.reputation import ReputationService
from app.utils.security import generate_captcha_token
from app.utils.redis_client import get_redis

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


@router.post("/captcha/verify", response_model=VerificationSubmitResponse)
async def submit_verification(
    request: VerificationSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit human verification response.

    1. Validate verification request
    2. Store verification response
    3. Update reputation
    4. Check for consensus
    5. Return CAPTCHA token
    """
    try:
        redis = await get_redis()

        # Validate verification request
        verification_data = await redis.get(f"verification:{request.verification_id}")
        if not verification_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification request not found or expired",
            )

        encoded_verification = verification_data.decode()
        if encoded_verification.startswith("{"):
            verification_context = json.loads(encoded_verification)
            session_id_str = verification_context["session_id"]
            prediction_id_str = verification_context["prediction_id"]
            audit_mode = verification_context.get("mode", "confirm")
        else:
            # Backward compatibility for verification requests created by a
            # server process running the pre-blind-audit format.
            session_id_str, prediction_id_str = encoded_verification.split(":")
            audit_mode = "confirm"
        session_id = uuid.UUID(session_id_str)
        prediction_id = uuid.UUID(prediction_id_str)

        # Validate session matches
        if str(session_id) != request.session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session mismatch",
            )

        # Get session and prediction
        session = await _get_session(db, session_id)
        prediction = await _get_prediction(db, prediction_id)

        if not session or not prediction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session or prediction not found",
            )

        if session.is_expired:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Session expired",
            )

        task = await _get_task(db, prediction.task_id)
        sample = await _get_sample(db, prediction.sample_id)
        if not task or not sample:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task or sample not found",
            )

        # Determine and validate the human-supplied label against the exact
        # model version pinned into the original inference assignment.
        shard_meta = (task.metadata_ or {}).get("shard_task", {})
        allowed_labels = [str(label) for label in shard_meta.get("labels", [])]
        if not allowed_labels:
            from app.ml.model_store import get_model_store

            model = get_model_store().get(shard_meta.get("model_name", ""))
            allowed_labels = list(model.labels) if model else []

        verified_label = _validate_human_label(
            request=request,
            prediction=prediction,
            allowed_labels=allowed_labels,
            audit_mode=audit_mode,
        )

        # Create the anonymous reputation record if this is the user's first
        # human audit. Only honeypot answers can update correctness before a
        # sample reaches independent consensus.
        reputation_service = ReputationService(db)
        reputation = await reputation_service.get_or_create_reputation(
            session.client_fingerprint or "anonymous"
        )
        reputation_at_vote = reputation.score

        duplicate_vote = await _has_prior_vote(
            db,
            sample_id=prediction.sample_id,
            fingerprint=session.client_fingerprint,
        )

        if not duplicate_vote:
            verification = Verification(
                prediction_id=prediction.id,
                sample_id=prediction.sample_id,
                session_id=session.id,
                response_type=request.response,
                original_label=prediction.predicted_label,
                verified_label=verified_label,
                response_time_ms=request.response_time_ms,
                reputation_score=reputation_at_vote,
            )
            db.add(verification)
            await db.flush()

            golden_service = GoldenDatasetService(db)
            await golden_service.process_verification(
                sample_id=prediction.sample_id,
                verified_label=verified_label,
                reputation_score=reputation_at_vote,
                domain=session.domain,
            )

            known_label = (sample.metadata_ or {}).get("known_label")
            if known_label is not None:
                reputation = await reputation_service.update_reputation(
                    session.client_fingerprint or "anonymous",
                    was_correct=verified_label == str(known_label),
                )
                await redis.setex(
                    f"reputation:{session.client_fingerprint}",
                    30 * 24 * 60 * 60,
                    str(reputation.score),
                )
                await redis.setex(
                    f"known_accuracy:{session.client_fingerprint}",
                    30 * 24 * 60 * 60,
                    str(reputation.accuracy),
                )
        else:
            logger.warning(
                "Ignoring duplicate human vote for sample %s from fingerprint %s",
                prediction.sample_id,
                (session.client_fingerprint or "anonymous")[:8],
            )

        # Generate CAPTCHA token
        captcha_token = generate_captcha_token(
            session_id=str(session.id),
            domain=session.domain,
        )
        expires_at = datetime.utcnow() + timedelta(
            seconds=settings.captcha_token_expiry_seconds
        )

        # Update session status
        session.status = "completed"
        session.completed_at = datetime.utcnow()

        # Delete verification request from Redis
        await redis.delete(f"verification:{request.verification_id}")

        await db.commit()

        logger.info(f"Verification completed: {session.id}")

        return VerificationSubmitResponse(
            success=True,
            captcha_token=captcha_token,
            expires_at=expires_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error submitting verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit verification",
        )


async def _get_session(db: AsyncSession, session_id: uuid.UUID) -> Optional[Session]:
    """Get session by UUID."""
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    return result.scalar_one_or_none()


async def _get_prediction(
    db: AsyncSession, prediction_id: uuid.UUID
) -> Optional[Prediction]:
    """Get prediction by UUID."""
    result = await db.execute(
        select(Prediction).where(Prediction.id == prediction_id)
    )
    return result.scalar_one_or_none()


async def _get_task(db: AsyncSession, task_id: uuid.UUID) -> Optional[Task]:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def _get_sample(db: AsyncSession, sample_id: uuid.UUID) -> Optional[Sample]:
    result = await db.execute(select(Sample).where(Sample.id == sample_id))
    return result.scalar_one_or_none()


async def _has_prior_vote(
    db: AsyncSession,
    *,
    sample_id: uuid.UUID,
    fingerprint: Optional[str],
) -> bool:
    if not fingerprint:
        return False
    result = await db.execute(
        select(Verification.id)
        .join(Session, Verification.session_id == Session.id)
        .where(
            Verification.sample_id == sample_id,
            Session.client_fingerprint == fingerprint,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _validate_human_label(
    *,
    request: VerificationSubmitRequest,
    prediction: Prediction,
    allowed_labels: list[str],
    audit_mode: str,
) -> str:
    if audit_mode == "blind" and not allowed_labels:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assigned model label taxonomy is unavailable",
        )

    if audit_mode == "blind" and request.response != "correct":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Blind audits require an independently selected label",
        )

    if request.response == "correct" and request.corrected_label:
        verified_label = request.corrected_label.strip()
    elif request.response == "confirm":
        verified_label = prediction.predicted_label
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A corrected label is required",
        )

    if allowed_labels and verified_label not in allowed_labels:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrected label is not valid for the assigned model",
        )
    return verified_label
