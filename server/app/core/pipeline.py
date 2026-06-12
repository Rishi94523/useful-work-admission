"""
Distributed inference pipeline coordinator.

ScaleAI-style data labeling, distributed across CAPTCHA solvers: each sample
flows through the model as a *pipeline run*. Individual users only compute a
segment of layers (sized by their risk tier so it fits in a few hundred ms),
the server verifies each segment cheaply (see proof_verifier), stores the
verified activation, and hands it to the next solver. When the last layer
completes, the pieced-together prediction becomes the sample's machine label,
which human verification later confirms into the golden dataset.
"""

from __future__ import annotations

import hashlib
import io
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.ml.model_store import ModelSpec, get_model_store
from app.ml.proof_verifier import VerificationReport
from app.models import PipelineRun, Sample

logger = logging.getLogger(__name__)
settings = get_settings()

# How many layers each risk tier computes per CAPTCHA. Low-risk users get a
# single layer (fastest); bot-like traffic must compute the whole model.
SEGMENT_LAYERS_BY_DIFFICULTY = {
    "normal": 1,
    "suspicious": 2,
    "bot_like": 99,  # clamped to remaining layers = full model
}

# A claimed segment is reassignable after this long without a submission.
CLAIM_TTL_SECONDS = 90


@dataclass
class SegmentAssignment:
    """A claimed unit of work: some layers of some run on some sample."""

    run: PipelineRun
    sample: Sample
    model: ModelSpec
    segment_start: int
    segment_end: int
    input_vector: List[float]

    @property
    def layer_count(self) -> int:
        return self.segment_end - self.segment_start


class PipelineCoordinator:
    """Claims, advances and completes distributed inference runs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def claim_segment(
        self,
        task_id: uuid.UUID,
        difficulty: str,
        model: Optional[ModelSpec] = None,
    ) -> SegmentAssignment:
        """
        Claim the next unit of work for a new CAPTCHA task.

        Prefers continuing an in-flight run (so partial computations get
        pieced together quickly); starts a new run on the least-served sample
        otherwise. When no model is pinned, in-flight runs of ANY loaded model
        are continued and new runs rotate randomly across the model store, so
        every architecture (dense MLP, CNN, …) keeps labeling its dataset.
        """
        store = get_model_store()
        segment_layers = SEGMENT_LAYERS_BY_DIFFICULTY.get(difficulty, 1)
        now = datetime.utcnow()

        run = await self._find_claimable_run(model, now)
        if run is None:
            if model is None:
                model = random.choice(store.list_models())
            sample = await self._select_sample()
            run = PipelineRun(
                sample_id=sample.id,
                model_name=model.name,
                model_version=model.version,
                next_layer=0,
                activation=None,
                status="in_progress",
                contributors=[],
            )
            self.db.add(run)
            await self.db.flush()
        else:
            model = store.get(run.model_name)
            sample = await self._get_sample(run.sample_id)

        segment_start = run.next_layer
        segment_end = min(segment_start + segment_layers, model.total_layers)

        run.claimed_by_task = task_id
        run.claimed_until = now + timedelta(seconds=CLAIM_TTL_SECONDS)
        await self.db.flush()

        if run.activation is not None:
            input_vector = [float(v) for v in run.activation]
        else:
            input_vector = model.preprocess_sample(sample.data_blob, sample.data_url)

        logger.debug(
            "Claimed segment [%d,%d) of run %s for task %s",
            segment_start,
            segment_end,
            run.id,
            task_id,
        )
        return SegmentAssignment(
            run=run,
            sample=sample,
            model=model,
            segment_start=segment_start,
            segment_end=segment_end,
            input_vector=input_vector,
        )

    async def _find_claimable_run(
        self, model: Optional[ModelSpec], now: datetime
    ) -> Optional[PipelineRun]:
        """
        Oldest in-flight, unclaimed (or claim-expired) run. When ``model`` is
        None, runs of any model still loaded at the same version qualify
        (version-isolated: runs for rotated-out checkpoints are never resumed).
        """
        query = (
            select(PipelineRun)
            .where(
                PipelineRun.status == "in_progress",
                or_(
                    PipelineRun.claimed_until.is_(None),
                    PipelineRun.claimed_until < now,
                ),
            )
            .order_by(PipelineRun.updated_at.asc())
        )
        if model is not None:
            query = query.where(
                PipelineRun.model_name == model.name,
                PipelineRun.model_version == model.version,
            )
            result = await self.db.execute(query.limit(1))
            return result.scalar_one_or_none()

        store = get_model_store()
        result = await self.db.execute(query.limit(20))
        for run in result.scalars().all():
            loaded = store.get(run.model_name)
            if loaded is not None and loaded.version == run.model_version:
                return run
        return None

    async def _select_sample(self) -> Sample:
        """Least-served sample; creates a synthetic fallback if pool is empty."""
        result = await self.db.execute(
            select(Sample).order_by(Sample.times_served.asc()).limit(10)
        )
        samples = result.scalars().all()
        if samples:
            sample = random.choice(samples)
        else:
            sample = await self._create_fallback_sample()
        sample.times_served += 1
        return sample

    async def _get_sample(self, sample_id: uuid.UUID) -> Sample:
        result = await self.db.execute(select(Sample).where(Sample.id == sample_id))
        sample = result.scalar_one_or_none()
        if sample is None:
            raise ValueError(f"Sample {sample_id} not found")
        return sample

    async def _create_fallback_sample(self) -> Sample:
        """Synthetic digit so the demo works before seed_data.py is run."""
        from PIL import Image, ImageDraw

        image = Image.new("L", (28, 28), color=0)
        draw = ImageDraw.Draw(image)
        draw.ellipse((7, 12, 21, 24), outline=255, width=3)
        draw.line((9, 14, 17, 4), fill=255, width=3)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()

        sample = Sample(
            data_type="image",
            model_type="mnist",
            data_hash=hashlib.sha256(image_bytes).hexdigest(),
            data_blob=image_bytes,
            metadata_={"width": 28, "height": 28, "channels": 1, "is_dummy": True},
        )
        self.db.add(sample)
        await self.db.flush()
        logger.warning("Sample pool empty — created fallback sample %s", sample.id)
        return sample

    async def get_run(self, run_id: uuid.UUID) -> Optional[PipelineRun]:
        result = await self.db.execute(
            select(PipelineRun).where(PipelineRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def advance(
        self,
        run: PipelineRun,
        session_id: uuid.UUID,
        segment_start: int,
        layer_count: int,
        report: VerificationReport,
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Advance a run with a verified segment result.

        Returns (run_completed, predicted_label, confidence).
        """
        if run.next_layer != segment_start:
            # Stale submission for a segment that was reassigned and finished.
            raise ValueError(
                f"Run {run.id} expects layer {run.next_layer}, "
                f"got segment starting at {segment_start}"
            )

        run.next_layer = segment_start + layer_count
        run.contributors = [
            *run.contributors,
            {
                "session_id": str(session_id),
                "segment": [segment_start, segment_start + layer_count],
                "at": datetime.utcnow().isoformat(),
            },
        ]
        run.claimed_by_task = None
        run.claimed_until = None

        model = get_model_store().get(run.model_name)
        completed = run.next_layer >= model.total_layers

        if completed:
            run.status = "completed"
            run.activation = None
            run.predicted_label = report.predicted_label
            run.confidence = report.confidence
            logger.info(
                "Pipeline run %s completed: label=%s conf=%.3f contributors=%d",
                run.id,
                run.predicted_label,
                run.confidence or 0.0,
                len(run.contributors),
            )
        else:
            run.activation = [float(v) for v in np.asarray(report.final_activation)]

        await self.db.flush()
        return completed, run.predicted_label, run.confidence

    async def release_claim(self, run: PipelineRun) -> None:
        """Release a claim after a failed submission so others can take over."""
        run.claimed_by_task = None
        run.claimed_until = None
        await self.db.flush()
