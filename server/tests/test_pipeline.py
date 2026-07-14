"""Concurrency and ownership checks for distributed pipeline leases."""

from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from sqlalchemy.dialects import postgresql

from app.core.pipeline import PipelineCoordinator
from app.ml.llm_layers import GQAAttentionLayer, SwigluMlpLayer
from app.ml.model_store import ModelSpec, apply_post_ops


@pytest.mark.asyncio
async def test_claim_query_skips_rows_locked_by_other_workers():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    coordinator = PipelineCoordinator(db)
    model = MagicMock(name="model")
    model.name = "test-model"
    model.version = "1.0.0"

    await coordinator._find_claimable_run(model, datetime.now(timezone.utc))

    statement = db.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql


@pytest.mark.asyncio
async def test_only_current_lease_owner_can_advance_a_run():
    coordinator = PipelineCoordinator(AsyncMock())
    run = MagicMock()
    run.id = uuid.uuid4()
    run.claimed_by_task = uuid.uuid4()

    with pytest.raises(ValueError, match="is not claimed by task"):
        await coordinator.advance(
            run=run,
            task_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            segment_start=0,
            layer_count=1,
            report=MagicMock(),
        )


def test_latency_planner_packs_small_models_but_caps_transformer_work():
    small = MagicMock()
    small.layers = [
        MagicMock(compute_ops=100_000),
        MagicMock(compute_ops=200_000),
        MagicMock(compute_ops=50_000),
    ]
    small.total_layers = len(small.layers)
    end, estimated, budget = PipelineCoordinator.plan_segment(
        small, 0, "normal", 250_000
    )
    assert (end, estimated, budget) == (3, 2, 200)

    transformer = MagicMock()
    transformer.layers = [
        MagicMock(compute_ops=60_555_264),
        MagicMock(compute_ops=52_297_728),
    ]
    transformer.total_layers = len(transformer.layers)
    end, estimated, budget = PipelineCoordinator.plan_segment(
        transformer, 0, "suspicious", 350_000
    )
    assert end == 1
    assert estimated == 243
    assert budget == 250
    assert PipelineCoordinator.model_fits_latency_target(
        transformer, 250_000
    )
    assert not PipelineCoordinator.model_fits_latency_target(
        transformer, 100_000
    )


def test_swiglu_microshards_preserve_the_original_residual_result():
    wg = np.asarray([[1, 0], [0, 1], [1, 1], [1, -1]], dtype=np.int8)
    wu = wg.copy()
    wd = np.asarray([[1, 0, 1, 0], [0, 1, 0, 1]], dtype=np.int8)
    source = SwigluMlpLayer(
        index=0,
        name="tiny_mlp",
        seq=1,
        d_model=2,
        ffn_dim=4,
        wg=wg,
        sg=np.ones(4, dtype=np.float32),
        wu=wu,
        su=np.ones(4, dtype=np.float32),
        wd=wd,
        sd=np.ones(2, dtype=np.float32),
        checksum="",
        post_ops=[{"op": "residual_input"}],
    )
    chunks = source.split(2)
    model = ModelSpec(
        name="tiny-transformer",
        version="1+ms2",
        task_type="classification",
        labels=["a", "b"],
        input_shape=[1, 2],
        preprocessing="",
        checksum="test",
        layers=chunks,
    )
    x = np.asarray([1.0, 2.0])
    source_z = source.forward(x)
    expected = apply_post_ops(source.z_output(source_z), source.post_ops, x)
    _, actual = model.forward_segment(x, 0, 2)

    assert chunks[0].input_size == 2
    assert chunks[1].input_size == 4
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_gqa_microshards_preserve_the_original_residual_result():
    rng = np.random.default_rng(4)
    weights = [
        rng.integers(-4, 5, size=(4, 4), dtype=np.int8) for _ in range(4)
    ]
    scales = [
        rng.uniform(0.01, 0.05, size=4).astype(np.float32) for _ in range(4)
    ]
    source = GQAAttentionLayer(
        index=0,
        name="tiny_gqa",
        seq=2,
        d_model=4,
        n_heads=2,
        n_kv_heads=2,
        head_dim=2,
        rope_theta=10_000.0,
        wq=weights[0],
        sq=scales[0],
        wk=weights[1],
        sk=scales[1],
        wv=weights[2],
        sv=scales[2],
        wo=weights[3],
        so=scales[3],
        bq=np.zeros(4, dtype=np.float32),
        bk=np.zeros(4, dtype=np.float32),
        bv=np.zeros(4, dtype=np.float32),
        checksum="",
        post_ops=[{"op": "residual_input"}],
    )
    chunks = source.split(2)
    model = ModelSpec(
        name="tiny-transformer",
        version="1+gqa2",
        task_type="classification",
        labels=["a", "b"],
        input_shape=[2, 4],
        preprocessing="",
        checksum="test-gqa",
        layers=chunks,
    )
    x = rng.normal(size=8)
    source_z = source.forward(x)
    expected = apply_post_ops(source.z_output(source_z), source.post_ops, x)
    _, actual = model.forward_segment(x, 0, 2)

    assert chunks[0].input_size == 8
    assert chunks[1].input_size == 16
    assert np.allclose(actual, expected, rtol=1e-12, atol=1e-12)
