"""Human-audit, reputation, and golden-dataset integrity tests."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.ml.inference_validator import InferenceValidator
from app.api.verification import _validate_human_label
from app.models import (
    GoldenDataset,
    Prediction,
    Sample,
    Session,
    Task,
    Verification,
)
from app.schemas import VerificationSubmitRequest
from app.services.golden_dataset import GoldenDatasetService


def test_verification_schema_rejects_label_free_reject_response():
    with pytest.raises(ValidationError):
        VerificationSubmitRequest(
            session_id=str(uuid.uuid4()),
            verification_id=str(uuid.uuid4()),
            response="reject",
        )


def test_blind_audit_requires_independent_model_specific_label():
    prediction = MagicMock()
    prediction.predicted_label = "positive"

    with pytest.raises(HTTPException, match="independently selected"):
        _validate_human_label(
            request=VerificationSubmitRequest(
                session_id=str(uuid.uuid4()),
                verification_id=str(uuid.uuid4()),
                response="confirm",
            ),
            prediction=prediction,
            allowed_labels=["negative", "positive"],
            audit_mode="blind",
        )

    with pytest.raises(HTTPException, match="not valid"):
        _validate_human_label(
            request=VerificationSubmitRequest(
                session_id=str(uuid.uuid4()),
                verification_id=str(uuid.uuid4()),
                response="correct",
                corrected_label="airplane",
            ),
            prediction=prediction,
            allowed_labels=["negative", "positive"],
            audit_mode="blind",
        )

    with pytest.raises(HTTPException, match="taxonomy is unavailable"):
        _validate_human_label(
            request=VerificationSubmitRequest(
                session_id=str(uuid.uuid4()),
                verification_id=str(uuid.uuid4()),
                response="correct",
                corrected_label="negative",
            ),
            prediction=prediction,
            allowed_labels=[],
            audit_mode="blind",
        )

    assert _validate_human_label(
        request=VerificationSubmitRequest(
            session_id=str(uuid.uuid4()),
            verification_id=str(uuid.uuid4()),
            response="correct",
            corrected_label="negative",
        ),
        prediction=prediction,
        allowed_labels=["negative", "positive"],
        audit_mode="blind",
    ) == "negative"


def test_zero_reputation_vote_does_not_gain_default_weight():
    zero_weight = MagicMock()
    zero_weight.verified_label = "negative"
    zero_weight.original_label = "negative"
    zero_weight.reputation_score = 0.0

    trusted = MagicMock()
    trusted.verified_label = "positive"
    trusted.original_label = "positive"
    trusted.reputation_score = 1.0

    consensus = GoldenDatasetService(MagicMock())._calculate_consensus(
        [zero_weight, trusted]
    )
    assert consensus["label"] == "positive"
    assert consensus["weighted_agreement"] == 1.0


def test_audit_probability_combines_site_rate_confidence_risk_and_honeypots():
    session = MagicMock()
    session.difficulty_tier = "normal"
    prediction = MagicMock()
    prediction.confidence = 0.99

    assert InferenceValidator.verification_probability(
        session=session,
        prediction=prediction,
        base_rate=0.12,
    ) == pytest.approx(0.12)

    prediction.confidence = 0.20
    assert InferenceValidator.verification_probability(
        session=session,
        prediction=prediction,
        base_rate=0.12,
    ) > 0.8

    session.difficulty_tier = "suspicious"
    prediction.confidence = 0.99
    assert InferenceValidator.verification_probability(
        session=session,
        prediction=prediction,
        base_rate=0.12,
    ) == pytest.approx(0.5)

    assert InferenceValidator.verification_probability(
        session=session,
        prediction=prediction,
        is_known_sample=True,
        base_rate=0.0,
    ) == 1.0


async def _add_vote(
    db,
    *,
    sample: Sample,
    fingerprint: str,
    label: str,
    reputation: float,
    created_at: datetime,
) -> Verification:
    session = Session(
        domain="example.test",
        session_token=str(uuid.uuid4()),
        risk_score=0.0,
        difficulty_tier="normal",
        client_fingerprint=fingerprint,
        status="completed",
        expires_at=datetime.utcnow() + timedelta(minutes=5),
    )
    db.add(session)
    await db.flush()

    task = Task(
        session_id=session.id,
        sample_id=sample.id,
        task_type="shard_inference",
        expected_time_ms=100,
        is_known_sample=False,
        status="completed",
        metadata_={},
    )
    db.add(task)
    await db.flush()

    prediction = Prediction(
        task_id=task.id,
        session_id=session.id,
        sample_id=sample.id,
        predicted_label=label,
        confidence=0.9,
        inference_time_ms=100,
        pow_hash="proof",
        is_valid=True,
    )
    db.add(prediction)
    await db.flush()

    verification = Verification(
        prediction_id=prediction.id,
        sample_id=sample.id,
        session_id=session.id,
        response_type="correct",
        original_label=label,
        verified_label=label,
        reputation_score=reputation,
        created_at=created_at,
    )
    db.add(verification)
    await db.flush()
    return verification


@pytest.mark.asyncio
async def test_consensus_counts_one_latest_vote_per_fingerprint(db_session):
    sample = Sample(
        data_type="text",
        model_type="sentiment",
        data_hash=uuid.uuid4().hex,
        data_blob=b"sample",
        metadata_={},
    )
    db_session.add(sample)
    await db_session.flush()

    now = datetime.utcnow()
    await _add_vote(
        db_session,
        sample=sample,
        fingerprint="same-browser",
        label="negative",
        reputation=1.0,
        created_at=now,
    )
    await _add_vote(
        db_session,
        sample=sample,
        fingerprint="same-browser",
        label="positive",
        reputation=1.0,
        created_at=now + timedelta(seconds=1),
    )
    await _add_vote(
        db_session,
        sample=sample,
        fingerprint="browser-2",
        label="positive",
        reputation=1.0,
        created_at=now + timedelta(seconds=2),
    )

    votes = await GoldenDatasetService(db_session)._get_sample_verifications(
        sample.id
    )
    assert len(votes) == 2
    assert [vote.final_label for vote in votes].count("positive") == 2


@pytest.mark.asyncio
async def test_three_independent_agreeing_votes_promote_golden_label(db_session):
    sample = Sample(
        data_type="image",
        model_type="digits",
        data_hash=uuid.uuid4().hex,
        data_blob=b"image",
        metadata_={},
    )
    db_session.add(sample)
    await db_session.flush()

    now = datetime.utcnow()
    for index in range(3):
        await _add_vote(
            db_session,
            sample=sample,
            fingerprint=f"browser-{index}",
            label="7",
            reputation=1.0 + index,
            created_at=now + timedelta(seconds=index),
        )

    promoted = await GoldenDatasetService(db_session).process_verification(
        sample_id=sample.id,
        verified_label="7",
        reputation_score=3.0,
        domain="example.test",
    )
    assert promoted is not None
    assert promoted.verified_label == "7"
    assert promoted.verification_count == 3

    stored = await db_session.scalar(
        select(GoldenDataset).where(GoldenDataset.sample_id == sample.id)
    )
    assert stored is promoted
