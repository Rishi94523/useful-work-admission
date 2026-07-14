"""Task Coordinator for assigning distributed shard-inference CAPTCHA tasks."""

import logging
import secrets
import uuid
from typing import Tuple
from dataclasses import dataclass, field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.config import get_settings
from app.models import Sample, Task
from app.ml.model_store import encode_input_data, get_model_store
from app.core.pipeline import PipelineCoordinator, SegmentAssignment

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class ShardTask:
    """Wire-ready configuration for one assigned segment."""

    task_id: uuid.UUID
    run_id: str
    sample_id: str
    model_name: str
    model_version: str
    shards: list = field(default_factory=list)
    input_data: str = ""
    input_shape: list = field(default_factory=list)
    segment_start: int = 0
    total_layers: int = 0
    expected_layers: int = 0
    difficulty: str = "normal"
    expected_time_ms: int = 0
    latency_budget_ms: int = 300
    labels: list = field(default_factory=list)
    model_checksum: str = ""
    # left-pad length for LLM attention masks (0 for image models)
    pad_len: int = 0
    # Public assignment nonce: binds the commitment and feeds a server-secret
    # HMAC that selects fresh hidden algebraic projection checks.
    verification_nonce: str = ""


class TaskCoordinator:
    """
    Coordinates ML task assignment based on risk and difficulty.

    Each task is one latency-budgeted *segment* of a distributed pipeline run.
    Small useful models can be packed to completion; large transformer
    operators are vertically microsharded so no risk tier receives a
    multi-second whole-model assignment. The server never executes the
    assigned layers itself — submissions are verified with the projection
    checks in proof_verifier.
    """

    DIFFICULTY_TIERS = {
        "normal": {
            "risk_score_max": 0.3,
            "inference_time_ms": 200,
            "verification_probability": 0.2,
        },
        "suspicious": {
            "risk_score_max": 0.7,
            "inference_time_ms": 250,
            "verification_probability": 0.5,
        },
        "bot_like": {
            "risk_score_max": 1.0,
            "inference_time_ms": 280,
            "verification_probability": 1.0,
        },
    }

    def __init__(self, db: AsyncSession, redis: Redis):
        self.db = db
        self.redis = redis
        self.pipeline = PipelineCoordinator(db)

    def get_difficulty_tier(self, risk_score: float) -> str:
        """Map a risk score (0.0-1.0) to a difficulty tier."""
        if risk_score <= self.DIFFICULTY_TIERS["normal"]["risk_score_max"]:
            return "normal"
        elif risk_score <= self.DIFFICULTY_TIERS["suspicious"]["risk_score_max"]:
            return "suspicious"
        return "bot_like"

    async def assign_task(
        self,
        session_id: uuid.UUID,
        difficulty: str,
        preferred_model: str | None = None,
        benchmark_ops_per_ms: float | None = None,
    ) -> Tuple[Task, Sample, ShardTask]:
        """
        Assign the next pipeline segment to a session.

        ``preferred_model`` pins a specific model (e.g. an LLM excluded from
        automatic rotation); unknown names fall back to normal rotation.
        Returns (Task row, Sample, wire-ready ShardTask).
        """
        task_id = uuid.uuid4()

        pinned = get_model_store().get(preferred_model) if preferred_model else None
        if pinned is not None and not self.pipeline.model_fits_latency_target(
            pinned, benchmark_ops_per_ms
        ):
            logger.info(
                "Client benchmark %.0f ops/ms cannot safely run %s; "
                "falling back to an auto-served small model",
                benchmark_ops_per_ms or 0.0,
                pinned.name,
            )
            pinned = None
        assignment: SegmentAssignment = await self.pipeline.claim_segment(
            task_id=task_id,
            difficulty=difficulty,
            model=pinned,
            benchmark_ops_per_ms=benchmark_ops_per_ms,
        )
        model = assignment.model
        verification_nonce = secrets.token_hex(16)

        shard_task = ShardTask(
            task_id=task_id,
            run_id=str(assignment.run.id),
            sample_id=str(assignment.sample.id),
            model_name=model.name,
            model_version=model.version,
            shards=model.shard_payloads(
                assignment.segment_start, assignment.segment_end
            ),
            input_data=encode_input_data(assignment.input_vector),
            input_shape=[1, len(assignment.input_vector)],
            segment_start=assignment.segment_start,
            total_layers=model.total_layers,
            expected_layers=assignment.layer_count,
            difficulty=difficulty,
            expected_time_ms=max(10, assignment.estimated_compute_ms),
            latency_budget_ms=assignment.latency_budget_ms,
            labels=model.labels,
            model_checksum=model.checksum,
            pad_len=int((assignment.context or {}).get("pad_len", 0)),
            verification_nonce=verification_nonce,
        )

        known_label = (assignment.sample.metadata_ or {}).get("known_label")

        task = Task(
            id=task_id,
            session_id=session_id,
            sample_id=assignment.sample.id,
            task_type="shard_inference",
            expected_time_ms=max(10, assignment.estimated_compute_ms),
            is_known_sample=known_label is not None,
            known_label=known_label,
            status="assigned",
            metadata_={
                "shard_task": {
                    "run_id": str(assignment.run.id),
                    "sample_id": str(assignment.sample.id),
                    "model_name": model.name,
                    "model_version": model.version,
                    "segment_start": assignment.segment_start,
                    "expected_layers": assignment.layer_count,
                    "difficulty": difficulty,
                    "model_checksum": model.checksum,
                    # The exact input the client must have used; the verifier
                    # replays projection checks against this.
                    "input_vector": [float(v) for v in assignment.input_vector],
                    # verification context (LLM pad mask etc.)
                    "context": assignment.context or {},
                    "verification_nonce": verification_nonce,
                    "estimated_compute_ms": assignment.estimated_compute_ms,
                    "latency_budget_ms": assignment.latency_budget_ms,
                    "benchmark_ops_per_ms": benchmark_ops_per_ms,
                }
            },
        )

        self.db.add(task)
        await self.db.flush()

        logger.debug(
            "Assigned segment [%d,%d) of run %s to task %s (difficulty %s)",
            assignment.segment_start,
            assignment.segment_end,
            assignment.run.id,
            task_id,
            difficulty,
        )
        return task, assignment.sample, shard_task

    async def get_task_stats(self) -> dict:
        """Get task assignment statistics."""
        result = await self.db.execute(
            select(
                Task.task_type,
                func.count(Task.id).label("count"),
            ).group_by(Task.task_type)
        )
        stats = {row.task_type: row.count for row in result}
        return {
            "task_counts": stats,
            "total_tasks": sum(stats.values()),
        }
