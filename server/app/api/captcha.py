"""
CAPTCHA API endpoints.

Flow:
  init   -> risk-score the client, claim the next pipeline segment, return
            model shards (with real checksums) + input activation
  submit -> verify the proof WITHOUT recomputing (projection checks), advance
            the distributed pipeline, optionally request human verification
            when a run completes, return the CAPTCHA token
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models import get_db, Session, Task, Sample, Prediction
from app.schemas import (
    CaptchaInitRequest,
    CaptchaInitResponse,
    CaptchaSubmitRequest,
    CaptchaSubmitResponse,
    CaptchaValidateResponse,
    ShardTaskInfo,
    PipelineProgressInfo,
    VerificationInfo,
    VerificationDisplayData,
    VerificationOption,
)
from app.core.task_coordinator import TaskCoordinator
from app.core.pipeline import PipelineCoordinator
from app.core.risk_scorer import RiskScorer
from app.ml.inference_validator import InferenceValidator
from app.utils.security import create_jwt_token, verify_jwt_token, generate_captcha_token
from app.utils.redis_client import get_redis
from app.services.site_registry import SiteRegistry, SiteRegistryError

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# In-memory inference log for dashboard visibility
inference_log = []


@router.post("/captcha/init", response_model=CaptchaInitResponse)
async def init_captcha(
    request: CaptchaInitRequest,
    db: AsyncSession = Depends(get_db),
    x_forwarded_for: Optional[str] = Header(default=None),
    origin: Optional[str] = Header(default=None),
    referer: Optional[str] = Header(default=None),
):
    """
    Initialize a new CAPTCHA session.

    1. Validate site key
    2. Compute risk score
    3. Assign difficulty tier (which sets the segment size)
    4. Claim the next distributed-pipeline segment
    5. Return session with shard task
    """
    try:
        client_ip = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else "unknown"

        redis = await get_redis()
        registry = SiteRegistry(db)
        try:
            registered_site = await registry.resolve_site(
                site_key=request.site_key,
                origin=origin,
                referer=referer,
            )
        except SiteRegistryError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(exc),
            )

        risk_scorer = RiskScorer(redis)
        task_coordinator = TaskCoordinator(db, redis)

        risk_score = await risk_scorer.compute_risk_score(
            client_ip=client_ip,
            user_agent=request.client_metadata.user_agent,
            site_key=request.site_key,
        )
        client_fingerprint = risk_scorer.generate_client_id(
            client_ip,
            request.client_metadata.user_agent,
        )
        adjusted_risk_score = min(
            1.0,
            risk_score * registered_site.config.difficulty_multiplier,
        )
        difficulty = task_coordinator.get_difficulty_tier(adjusted_risk_score)

        session_token = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(seconds=settings.captcha_token_expiry_seconds)

        session = Session(
            domain=registered_site.config.domain,
            session_token=session_token,
            risk_score=adjusted_risk_score,
            difficulty_tier=difficulty,
            client_fingerprint=client_fingerprint,
            status="pending",
            expires_at=expires_at,
        )
        db.add(session)
        await db.flush()

        task, sample, shard_task = await task_coordinator.assign_task(
            session_id=session.id,
            difficulty=difficulty,
        )
        task.metadata_ = {
            **(task.metadata_ or {}),
            "site_key_prefix": registered_site.site_key_prefix,
        }

        challenge_token = create_jwt_token(
            data={
                "session_id": str(session.id),
                "task_id": str(task.id),
                "difficulty": difficulty,
                "domain": registered_site.config.domain,
                "site_key_prefix": registered_site.site_key_prefix,
            },
            expires_delta=timedelta(seconds=settings.captcha_token_expiry_seconds),
        )

        task_info = ShardTaskInfo(
            task_id=str(task.id),
            run_id=shard_task.run_id,
            sample_id=shard_task.sample_id,
            model_name=shard_task.model_name,
            model_version=shard_task.model_version,
            shards=shard_task.shards,
            input_data=shard_task.input_data,
            input_shape=shard_task.input_shape,
            segment_start=shard_task.segment_start,
            total_layers=shard_task.total_layers,
            expected_layers=shard_task.expected_layers,
            difficulty=shard_task.difficulty,
            expected_time_ms=shard_task.expected_time_ms,
            labels=shard_task.labels,
            model_checksum=shard_task.model_checksum,
        )

        await db.commit()

        logger.info(
            "Session initialized: %s, difficulty: %s, segment [%d,%d) of run %s",
            session.id,
            difficulty,
            shard_task.segment_start,
            shard_task.segment_start + shard_task.expected_layers,
            shard_task.run_id,
        )

        return CaptchaInitResponse(
            session_id=str(session.id),
            challenge_token=challenge_token,
            task=task_info,
            difficulty=difficulty,
            expires_at=expires_at,
        )

    except Exception as e:
        logger.exception(f"Error initializing CAPTCHA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize CAPTCHA",
        )


@router.post("/captcha/submit", response_model=CaptchaSubmitResponse)
async def submit_captcha(
    request: CaptchaSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a computed segment.

    1. Validate session/task
    2. Verify proof of computation (projection checks — no recomputation)
    3. Advance the distributed pipeline with the verified activation
    4. If the run completed, maybe ask this human to verify the label
    5. Return CAPTCHA token
    """
    try:
        redis = await get_redis()
        validator = InferenceValidator(db, redis)
        pipeline = PipelineCoordinator(db)

        session = await _get_session(db, request.session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if session.is_expired:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Session expired")

        task = await _get_task(db, request.task_id, session.id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

        report = await validator.validate_submission(
            task=task,
            proof=request.proof,
            prediction=request.prediction,
            timing=request.timing,
        )

        shard_meta = (task.metadata_ or {}).get("shard_task", {})
        run_id = shard_meta.get("run_id")
        segment_start = shard_meta.get("segment_start", 0)
        expected_layers = shard_meta.get("expected_layers", 0)
        run = await pipeline.get_run(uuid.UUID(run_id)) if run_id else None

        if not report.valid:
            risk_scorer = RiskScorer(redis)
            await risk_scorer.record_proof_outcome(
                client_id=session.client_fingerprint,
                site_key_prefix=(task.metadata_ or {}).get("site_key_prefix"),
                valid=False,
                reason=report.reason,
                completion_time_ms=request.timing.total_ms,
            )
            session.status = "failed"
            task.status = "failed"
            if run is not None and run.claimed_by_task == task.id:
                await pipeline.release_claim(run)
            await db.commit()
            logger.warning(
                "CAPTCHA validation failed: %s (%s)", session.id, report.reason
            )
            return CaptchaSubmitResponse(success=False, requires_verification=False)

        # Advance the distributed pipeline with the verified result
        run_completed = False
        predicted_label = None
        confidence = None
        contributors = 1
        if run is not None:
            try:
                run_completed, predicted_label, confidence = await pipeline.advance(
                    run=run,
                    session_id=session.id,
                    segment_start=segment_start,
                    layer_count=expected_layers,
                    report=report,
                )
                contributors = len(run.contributors)
            except ValueError:
                # Claim expired and another solver advanced this run. The
                # user's work was still verified valid — credit them anyway.
                logger.info("Stale segment for run %s; crediting solver only", run_id)

        task.status = "completed"
        risk_scorer = RiskScorer(redis)
        await risk_scorer.record_proof_outcome(
            client_id=session.client_fingerprint,
            site_key_prefix=(task.metadata_ or {}).get("site_key_prefix"),
            valid=True,
            completion_time_ms=request.timing.total_ms,
        )

        # Record the pieced-together prediction when the run completes
        prediction_row = None
        if run_completed:
            prediction_row = Prediction(
                task_id=task.id,
                session_id=session.id,
                sample_id=task.sample_id,
                predicted_label=predicted_label,
                confidence=confidence,
                inference_time_ms=request.timing.inference_ms,
                pow_hash=request.proof.proof_hash,
                is_valid=True,
            )
            db.add(prediction_row)
            await db.flush()

            # Honeypot check: known samples should match the model prediction
            if task.is_known_sample and task.known_label:
                if predicted_label.lower() != task.known_label.lower():
                    logger.info(
                        "Known-sample mismatch on run %s: predicted=%s expected=%s",
                        run_id,
                        predicted_label,
                        task.known_label,
                    )

        await _log_inference(
            db,
            task,
            session,
            report,
            request,
            run_id=run_id,
            segment_start=segment_start,
            expected_layers=expected_layers,
            run_completed=run_completed,
            predicted_label=predicted_label,
            confidence=confidence,
        )

        from app.ml.model_store import get_model_store

        model = get_model_store().get(shard_meta.get("model_name", ""))
        pipeline_info = PipelineProgressInfo(
            run_id=run_id or "",
            layers_done=(run.next_layer if run else segment_start + expected_layers),
            total_layers=model.total_layers if model else segment_start + expected_layers,
            completed=run_completed,
            predicted_label=predicted_label,
            confidence=confidence,
            contributors=contributors,
        )

        # Human verification only makes sense once a run has a final label
        requires_verification = False
        if run_completed and prediction_row is not None:
            requires_verification = await validator.should_require_verification(
                session=session,
                prediction=prediction_row,
            )

        if requires_verification:
            verification_id = str(uuid.uuid4())
            sample_result = await db.execute(
                select(Sample).where(Sample.id == task.sample_id)
            )
            sample = sample_result.scalar_one_or_none()

            await redis.setex(
                f"verification:{verification_id}",
                settings.captcha_token_expiry_seconds,
                f"{session.id}:{prediction_row.id}",
            )

            session.status = "verifying"
            await db.commit()

            return CaptchaSubmitResponse(
                success=True,
                requires_verification=True,
                pipeline=pipeline_info,
                verification=VerificationInfo(
                    verification_id=verification_id,
                    display_data=VerificationDisplayData(
                        type=sample.data_type,
                        url=sample.data_url,
                        content=_encode_sample_data(sample) if not sample.data_url else None,
                    ),
                    predicted_label=predicted_label,
                    prompt=f"Is this a {predicted_label}?",
                    options=[
                        VerificationOption(id="confirm", label="Yes, correct", type="confirm"),
                        VerificationOption(id="correct", label="Choose correct label", type="correct"),
                    ],
                ),
            )

        captcha_token = generate_captcha_token(
            session_id=str(session.id),
            domain=session.domain,
            site_key_prefix=(task.metadata_ or {}).get("site_key_prefix"),
            work_units=expected_layers,
        )
        expires_at = datetime.utcnow() + timedelta(
            seconds=settings.captcha_token_expiry_seconds
        )

        session.status = "completed"
        session.completed_at = datetime.utcnow()
        await db.commit()

        logger.info(f"CAPTCHA completed: {session.id}")

        return CaptchaSubmitResponse(
            success=True,
            requires_verification=False,
            captcha_token=captcha_token,
            expires_at=expires_at,
            pipeline=pipeline_info,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error submitting CAPTCHA: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit CAPTCHA",
        )


async def _log_inference(
    db: AsyncSession,
    task: Task,
    session: Session,
    report,
    request: CaptchaSubmitRequest,
    *,
    run_id: Optional[str],
    segment_start: int,
    expected_layers: int,
    run_completed: bool,
    predicted_label: Optional[str],
    confidence: Optional[float],
) -> None:
    """Append a record to the in-memory dashboard log."""
    sample_result = await db.execute(select(Sample).where(Sample.id == task.sample_id))
    sample = sample_result.scalar_one_or_none()

    image_url = None
    if sample:
        if sample.data_blob:
            image_url = f"/api/v1/sample/{task.sample_id}/image"
        elif sample.data_url:
            image_url = sample.data_url

    record = {
        "id": str(task.id),
        "session_id": str(session.id),
        "task_id": str(task.id),
        "sample_id": str(task.sample_id),
        "run_id": run_id,
        "segment": [segment_start, segment_start + expected_layers],
        "run_completed": run_completed,
        "image_url": image_url,
        "predicted_label": predicted_label or "(partial)",
        "confidence": confidence or 0.0,
        "top_k": [
            {"label": p.label, "confidence": p.confidence}
            for p in (request.prediction.top_k if request.prediction else [])
        ],
        "inference_ms": request.timing.inference_ms,
        "total_ms": request.timing.total_ms,
        "timestamp": datetime.utcnow().isoformat(),
        "is_valid": report.valid,
        "checks": report.checks_run,
        "audited": report.audited,
    }
    inference_log.append(record)
    if len(inference_log) > 500:
        inference_log.pop(0)


@router.get("/captcha/validate/{token}", response_model=CaptchaValidateResponse)
async def validate_captcha(
    token: str,
    db: AsyncSession = Depends(get_db),
    x_pouw_secret_key: Optional[str] = Header(default=None),
):
    """
    Validate a CAPTCHA token (server-to-server).

    This endpoint is called by the website's backend to verify
    that a CAPTCHA token is valid.
    """
    try:
        payload = verify_jwt_token(token)
        if not payload:
            return CaptchaValidateResponse(valid=False)
        if payload.get("type") != "captcha_token":
            return CaptchaValidateResponse(valid=False)
        token_id = payload.get("jti")
        if not token_id:
            return CaptchaValidateResponse(valid=False)

        session_id = payload.get("session_id")
        if not session_id:
            return CaptchaValidateResponse(valid=False)

        session = await _get_session(db, session_id)
        if not session or session.status != "completed":
            return CaptchaValidateResponse(valid=False)
        if payload.get("domain") != session.domain:
            return CaptchaValidateResponse(valid=False)
        if not x_pouw_secret_key:
            return CaptchaValidateResponse(valid=False)

        registry = SiteRegistry(db)
        secret_ok = await registry.validate_secret_for_domain(
            domain=session.domain,
            secret_key=x_pouw_secret_key,
        )
        if not secret_ok:
            return CaptchaValidateResponse(valid=False)

        redis = await get_redis()
        replay_key = f"captcha_token_used:{token_id}"
        if await redis.get(replay_key):
            return CaptchaValidateResponse(valid=False)
        await redis.setex(
            replay_key,
            settings.captcha_token_expiry_seconds,
            str(session.id),
        )

        token_exp = payload.get("exp")
        if token_exp and datetime.fromtimestamp(token_exp) < datetime.utcnow():
            return CaptchaValidateResponse(valid=False)

        return CaptchaValidateResponse(
            valid=True,
            session_id=str(session.id),
            domain=session.domain,
            completed_at=session.completed_at,
            difficulty=session.difficulty_tier,
            verification_performed=len(session.verifications) > 0,
        )

    except Exception as e:
        logger.exception(f"Error validating CAPTCHA: {e}")
        return CaptchaValidateResponse(valid=False)


def _encode_sample_data(sample: Sample) -> Optional[str]:
    """Encode sample data to base64."""
    import base64

    if sample.data_blob:
        return base64.b64encode(sample.data_blob).decode("utf-8")
    return None


async def _get_session(db: AsyncSession, session_id: str) -> Optional[Session]:
    """Get session by ID."""
    try:
        session_uuid = uuid.UUID(session_id)
        result = await db.execute(
            select(Session).where(Session.id == session_uuid)
        )
        return result.scalar_one_or_none()
    except ValueError:
        return None


async def _get_task(
    db: AsyncSession, task_id: str, session_id: uuid.UUID
) -> Optional[Task]:
    """Get task by ID and session."""
    try:
        task_uuid = uuid.UUID(task_id)
        result = await db.execute(
            select(Task).where(
                Task.id == task_uuid,
                Task.session_id == session_id,
            )
        )
        return result.scalar_one_or_none()
    except ValueError:
        return None


@router.get("/sample/{sample_id}/image")
async def get_sample_image(
    sample_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Serve sample image from database blob."""
    try:
        sample_uuid = uuid.UUID(sample_id)
        result = await db.execute(
            select(Sample).where(Sample.id == sample_uuid)
        )
        sample = result.scalar_one_or_none()

        if not sample:
            raise HTTPException(status_code=404, detail="Sample not found")

        if sample.data_blob:
            content_type = "image/png"
            if sample.data_type == "image":
                if sample.data_blob[:3] == b'\xff\xd8\xff':
                    content_type = "image/jpeg"
                elif sample.data_blob[:8] == b'\x89PNG\r\n\x1a\n':
                    content_type = "image/png"

            return Response(content=sample.data_blob, media_type=content_type)
        elif sample.data_url:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=sample.data_url)
        else:
            raise HTTPException(status_code=404, detail="No image data available")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sample ID")


@router.get("/pipeline/runs")
async def get_pipeline_runs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Recent distributed pipeline runs: the piecing-together view."""
    from app.models import PipelineRun

    result = await db.execute(
        select(PipelineRun).order_by(PipelineRun.updated_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return {
        "runs": [
            {
                "run_id": str(r.id),
                "sample_id": str(r.sample_id),
                "model": f"{r.model_name}@{r.model_version}",
                "status": r.status,
                "layers_done": r.next_layer,
                "predicted_label": r.predicted_label,
                "confidence": r.confidence,
                "contributors": r.contributors,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in runs
        ]
    }
