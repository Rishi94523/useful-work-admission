"""Operational and research/economics metrics endpoints."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ml.model_store import get_model_store
from app.ml.proof_verifier import NUM_PROJECTIONS
from app.models import GoldenDataset, PipelineRun, Prediction, Session, Task, Verification, get_db

settings = get_settings()
router = APIRouter()


@router.get("/metrics/economics")
async def get_economics_metrics(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """
    Return useful-work, anti-abuse, and rough economics metrics.

    Dollar estimates are deliberately separated from raw operation counts so
    papers/grants can swap in a more defensible cost model later.
    """
    session_counts = await _count_by(db, Session.status)
    task_counts = await _count_by(db, Task.status)
    pipeline_counts = await _count_by(db, PipelineRun.status)

    task_result = await db.execute(select(Task))
    tasks = task_result.scalars().all()

    assigned_ops = 0
    verified_ops = 0
    projection_verify_ops = 0
    assigned_segments = 0
    verified_segments = 0
    segment_histogram: Counter[str] = Counter()

    model_store = get_model_store()
    for task in tasks:
        meta = (task.metadata_ or {}).get("shard_task", {})
        model = model_store.get(meta.get("model_name", ""))
        if model is None:
            continue

        start = int(meta.get("segment_start", 0))
        count = int(meta.get("expected_layers", 0))
        end = min(start + count, model.total_layers)
        if end <= start:
            continue

        # Layer-type-generic accounting: dense and conv layers both report
        # their true multiply-accumulate cost and O(in+out) projection cost.
        segment_ops = 0
        segment_verify_ops = 0
        for layer in model.layers[start:end]:
            segment_ops += layer.compute_ops
            segment_verify_ops += NUM_PROJECTIONS * layer.projection_ops

        assigned_segments += 1
        assigned_ops += segment_ops
        projection_verify_ops += segment_verify_ops
        segment_histogram[f"{start}-{end}"] += 1

        if task.status == "completed":
            verified_segments += 1
            verified_ops += segment_ops

    prediction_count = await _scalar_count(db, Prediction.id)
    verification_count = await _scalar_count(db, Verification.id)
    golden_count = await _scalar_count(db, GoldenDataset.id)
    completed_runs = pipeline_counts.get("completed", 0)
    failed_tasks = task_counts.get("failed", 0)

    compute_cost = verified_ops / 1_000_000_000 * settings.estimated_compute_usd_per_billion_ops
    label_value = verification_count * settings.estimated_label_value_usd
    avoided_verify_ops = max(0, verified_ops - projection_verify_ops)

    return {
        "sessions": {
            "total": sum(session_counts.values()),
            "by_status": session_counts,
        },
        "tasks": {
            "total": sum(task_counts.values()),
            "by_status": task_counts,
            "assigned_segments": assigned_segments,
            "verified_segments": verified_segments,
            "failed_segments": failed_tasks,
            "segment_histogram": dict(segment_histogram),
        },
        "pipeline": {
            "by_status": pipeline_counts,
            "completed_runs": completed_runs,
            "machine_labels": prediction_count,
            "human_verifications": verification_count,
            "golden_labels": golden_count,
        },
        "work": {
            "assigned_compute_ops": assigned_ops,
            "verified_compute_ops": verified_ops,
            "routine_projection_verify_ops": projection_verify_ops,
            "estimated_ops_saved_vs_recompute": avoided_verify_ops,
            "verification_asymmetry_ratio": (
                round(verified_ops / projection_verify_ops, 3)
                if projection_verify_ops
                else None
            ),
            "num_secret_projections": NUM_PROJECTIONS,
        },
        "economics": {
            "estimated_compute_cost_usd": round(compute_cost, 6),
            "estimated_label_value_usd": round(label_value, 6),
            "estimated_net_captured_value_usd": round(label_value + compute_cost, 6),
            "assumptions": {
                "compute_usd_per_billion_ops": settings.estimated_compute_usd_per_billion_ops,
                "label_value_usd": settings.estimated_label_value_usd,
            },
        },
        "abuse_pressure": {
            "failed_task_rate": (
                round(failed_tasks / max(1, sum(task_counts.values())), 4)
            ),
            "proof_failures_observed": failed_tasks,
        },
    }


async def _count_by(db: AsyncSession, column) -> dict[str, int]:
    result = await db.execute(select(column, func.count()).group_by(column))
    return {str(status): int(count) for status, count in result.all()}


async def _scalar_count(db: AsyncSession, column) -> int:
    result = await db.execute(select(func.count(column)))
    return int(result.scalar_one())
