"""Concurrency and ownership checks for distributed pipeline leases."""

from datetime import datetime, timezone
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.core.pipeline import PipelineCoordinator


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
