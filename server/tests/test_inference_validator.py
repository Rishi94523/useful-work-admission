"""Security-boundary checks for inference submission validation."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.ml.inference_validator import InferenceValidator
from app.schemas import InferenceProofData, TimingData


@pytest.mark.asyncio
async def test_production_task_without_assignment_challenge_is_rejected():
    task = MagicMock()
    task.id = uuid.uuid4()
    task.expected_time_ms = 100
    task.metadata_ = {
        "shard_task": {
            "model_name": "mnist-tiny",
            "sample_id": "sample-1",
            "segment_start": 0,
            "expected_layers": 1,
            "input_vector": [0.0] * 784,
        }
    }
    proof = InferenceProofData(
        task_id=str(task.id),
        sample_id="sample-1",
        segment_start=0,
        layer_count=1,
        pre_activations=[[0.0]],
        output_hashes=["unused"],
        proof_hash="unused",
        timestamp=0,
    )
    timing = TimingData(
        model_load_ms=0,
        inference_ms=100,
        total_ms=100,
        started_at=0,
        completed_at=100,
    )

    report = await InferenceValidator(MagicMock(), MagicMock()).validate_submission(
        task=task,
        proof=proof,
        prediction=None,
        timing=timing,
    )

    assert not report.valid
    assert report.reason == "task missing verification challenge"
