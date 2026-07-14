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

# Compute budgets replace the old static layer counts. A layer can vary from
# microseconds (tiny dense head) to seconds (an unsplit transformer MLP), so a
# count is not a meaningful latency control. Client throughput is measured by
# the widget with the same kind of dense loops used by the shard engine and is
# conservatively clamped before it affects assignment size.
LATENCY_BUDGET_MS_BY_DIFFICULTY = {
    "normal": 200,
    "suspicious": 250,
    "bot_like": 280,
}
DEFAULT_BROWSER_OPS_PER_MS = 250_000.0
MIN_BROWSER_OPS_PER_MS = 25_000.0
MAX_BROWSER_OPS_PER_MS = 250_000.0
MAX_ASSIGNMENT_TARGET_MS = 300

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
    # extra verification context (e.g. pad_len for LLM attention masks)
    context: dict = None
    estimated_compute_ms: int = 0
    latency_budget_ms: int = 300

    @property
    def layer_count(self) -> int:
        return self.segment_end - self.segment_start


class PipelineCoordinator:
    """Claims, advances and completes distributed inference runs."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def normalized_ops_per_ms(
        benchmark_ops_per_ms: Optional[float] = None,
    ) -> float:
        reported = benchmark_ops_per_ms or DEFAULT_BROWSER_OPS_PER_MS
        return min(
            MAX_BROWSER_OPS_PER_MS,
            max(MIN_BROWSER_OPS_PER_MS, float(reported)),
        )

    @classmethod
    def model_fits_latency_target(
        cls,
        model: ModelSpec,
        benchmark_ops_per_ms: Optional[float] = None,
        target_ms: int = MAX_ASSIGNMENT_TARGET_MS,
    ) -> bool:
        """Whether every indivisible runtime stage fits the device target."""
        ops_per_ms = cls.normalized_ops_per_ms(benchmark_ops_per_ms)
        return all(
            (float(layer.compute_ops) / ops_per_ms) <= target_ms
            for layer in model.layers
        )

    @staticmethod
    def plan_segment(
        model: ModelSpec,
        segment_start: int,
        difficulty: str,
        benchmark_ops_per_ms: Optional[float] = None,
    ) -> Tuple[int, int, int]:
        """Return ``(end, estimated_ms, budget_ms)`` for one browser task."""
        budget_ms = LATENCY_BUDGET_MS_BY_DIFFICULTY.get(difficulty, 200)
        ops_per_ms = PipelineCoordinator.normalized_ops_per_ms(
            benchmark_ops_per_ms
        )

        end = segment_start
        total_ops = 0
        while end < model.total_layers:
            layer_ops = int(model.layers[end].compute_ops)
            candidate_ms = (total_ops + layer_ops) / ops_per_ms
            if end > segment_start and candidate_ms > budget_ms:
                break
            total_ops += layer_ops
            end += 1

        # A single indivisible layer is always assigned even when its estimate
        # is above budget. Production transformer attention and MLP operators
        # are split below that limit at model-load time, which makes this
        # exceptional path visible instead of silently constructing an
        # unfinishable empty task.
        if end == segment_start:
            total_ops = int(model.layers[end].compute_ops)
            end += 1
        estimated_ms = max(1, int(np.ceil(total_ops / ops_per_ms)))
        return end, estimated_ms, budget_ms

    async def claim_segment(
        self,
        task_id: uuid.UUID,
        difficulty: str,
        model: Optional[ModelSpec] = None,
        benchmark_ops_per_ms: Optional[float] = None,
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
        now = datetime.utcnow()

        run = await self._find_claimable_run(model, now)
        if run is None:
            if model is None:
                # browser rotation only serves models every client can run
                model = random.choice(
                    [m for m in store.list_models() if m.auto_serve]
                )
            sample = await self._select_sample(model)
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
        segment_end, estimated_compute_ms, latency_budget_ms = self.plan_segment(
            model,
            segment_start,
            difficulty,
            benchmark_ops_per_ms,
        )

        run.claimed_by_task = task_id
        run.claimed_until = now + timedelta(seconds=CLAIM_TTL_SECONDS)
        await self.db.flush()

        # verification context: deterministic per sample, needed by EVERY
        # segment of a text run (attention pad mask), so recompute cheaply
        context = {}
        if model.input_kind == "text":
            text = (sample.data_blob or b"").decode("utf-8", errors="replace")
            _, pad_len = model.tokenize_prompt(text)
            context["pad_len"] = pad_len

        if run.activation is not None:
            input_vector = [float(v) for v in run.activation]
        else:
            input_vector, prep_context = model.prepare_input(
                sample.data_blob, sample.data_url
            )
            context.update(prep_context)

        # The wire format is float32. Canonicalizing here ensures the verifier
        # checks the exact activation the browser decodes, including partial
        # accumulator handoffs between independent sessions.
        input_vector = [
            float(v) for v in np.asarray(input_vector, dtype=np.float32)
        ]

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
            context=context,
            estimated_compute_ms=estimated_compute_ms,
            latency_budget_ms=latency_budget_ms,
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
            .with_for_update(skip_locked=True)
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
            if (
                loaded is not None
                and loaded.version == run.model_version
                and loaded.auto_serve
            ):
                return run
        return None

    async def _select_sample(self, model: ModelSpec) -> Sample:
        """
        Least-served sample of the model's input kind (image models get
        image samples, text/LLM models get text samples); synthesizes a
        fallback if the pool is empty.
        """
        data_type = "text" if model.input_kind == "text" else "image"
        result = await self.db.execute(
            select(Sample)
            .where(Sample.data_type == data_type)
            .order_by(Sample.times_served.asc())
            .limit(10)
        )
        samples = result.scalars().all()
        if samples:
            sample = random.choice(samples)
        elif data_type == "text":
            sample = await self._create_fallback_text_sample()
        else:
            sample = await self._create_fallback_sample()
        sample.times_served += 1
        return sample

    async def _create_fallback_text_sample(self) -> Sample:
        """Synthetic review so LLM runs work before text seeding."""
        text = "The product exceeded all my expectations, truly fantastic!"
        blob = text.encode("utf-8")
        sample = Sample(
            data_type="text",
            model_type="sentiment",
            data_hash=hashlib.sha256(blob).hexdigest(),
            data_blob=blob,
            metadata_={"true_label": "positive", "is_dummy": True},
        )
        self.db.add(sample)
        await self.db.flush()
        logger.warning("Text sample pool empty — created fallback sample %s", sample.id)
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

    async def get_run(
        self, run_id: uuid.UUID, *, for_update: bool = False
    ) -> Optional[PipelineRun]:
        query = select(PipelineRun).where(PipelineRun.id == run_id)
        if for_update:
            query = query.with_for_update()
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def advance(
        self,
        run: PipelineRun,
        task_id: uuid.UUID,
        session_id: uuid.UUID,
        segment_start: int,
        layer_count: int,
        report: VerificationReport,
    ) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        Advance a run with a verified segment result.

        Returns (run_completed, predicted_label, confidence).
        """
        if run.claimed_by_task != task_id:
            raise ValueError(
                f"Run {run.id} is not claimed by task {task_id}"
            )
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
