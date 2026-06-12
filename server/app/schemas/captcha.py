"""CAPTCHA API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class APIModel(BaseModel):
    """Base schema with snake_case input and camelCase serialization support."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
    )


class ClientMetadata(APIModel):
    user_agent: str = Field(..., description="Browser user agent")
    language: str = Field(..., description="Browser language")
    timezone: str = Field(..., description="Client timezone")
    screen_width: Optional[int] = Field(default=None, description="Screen width")
    screen_height: Optional[int] = Field(default=None, description="Screen height")


class CaptchaInitRequest(APIModel):
    site_key: str = Field(..., min_length=10, description="Site API key")
    client_metadata: ClientMetadata = Field(..., description="Client information")


class ModelMeta(APIModel):
    name: str
    version: str
    input_shape: List[int]
    labels: List[str]
    checksum: str


class PostOpConfig(APIModel):
    """A cheap transform applied after a provable layer (relu, maxpool2d, …)."""

    op: str
    pool: Optional[int] = None
    shape: Optional[List[int]] = Field(
        default=None,
        description="(C, H, W) shape of the tensor entering a maxpool2d op",
    )


class NeuralLayerConfig(APIModel):
    name: str
    type: str
    weights: List[float]
    biases: List[float]
    input_shape: List[int]
    output_shape: List[int]
    activation: str
    kernel: Optional[List[int]] = Field(
        default=None, description="(kh, kw) for conv2d layers"
    )
    post_ops: List[PostOpConfig] = Field(
        default_factory=list,
        description="Post-op chain the client applies before the next layer",
    )


class ModelShardInfo(APIModel):
    index: int
    name: str
    layer_type: str
    input_shape: List[int]
    output_shape: List[int]
    activation: Optional[str] = None
    checksum: str = Field(
        default="",
        description="SHA-256 over the layer's float32 wire bytes; clients "
        "verify this before executing",
    )
    layers: List[NeuralLayerConfig] = Field(default_factory=list)


class TaskInfo(APIModel):
    task_id: str
    model_url: str
    sample_data: Optional[str] = None
    sample_url: Optional[str] = None
    sample_type: str
    task_type: str
    expected_time_ms: int
    model_meta: ModelMeta


class ShardTaskInfo(APIModel):
    task_id: str
    sample_id: str
    run_id: str = Field(
        default="",
        description="Distributed pipeline run this segment belongs to",
    )
    model_name: str
    model_version: str
    shards: List[ModelShardInfo]
    input_data: str
    input_shape: List[int]
    segment_start: int = Field(
        default=0,
        description="Index of the first layer in this segment; >0 means the "
        "input is the verified activation handed over from a previous solver",
    )
    total_layers: int = Field(default=0, description="Total layers in the model")
    expected_layers: int
    difficulty: str
    expected_time_ms: int
    labels: List[str]
    model_checksum: str


class CaptchaInitResponse(APIModel):
    session_id: str
    challenge_token: str
    task: TaskInfo | ShardTaskInfo
    difficulty: str
    expires_at: datetime


class TopKPrediction(APIModel):
    label: str
    confidence: float = Field(..., ge=0, le=1)


class PredictionData(APIModel):
    label: str
    confidence: float = Field(..., ge=0, le=1)
    top_k: List[TopKPrediction]


class ProofOfWorkData(APIModel):
    hash: str = Field(..., min_length=64)
    nonce: int = Field(..., ge=0)
    model_checksum: str
    input_hash: str
    output_hash: str


class InferenceProofData(APIModel):
    task_id: str
    sample_id: str
    segment_start: int = Field(default=0, ge=0)
    layer_count: int = Field(..., ge=1)
    pre_activations: List[List[float]] = Field(
        ...,
        min_length=1,
        description="Pre-activation output vector of each computed layer; "
        "verified server-side via secret projection checks without "
        "re-running the computation",
    )
    output_hashes: List[str] = Field(..., min_length=1)
    prediction_hash: str = Field(
        default="",
        description="Hash of the prediction; only set on final segments",
    )
    proof_hash: str
    timestamp: int


class TimingData(APIModel):
    model_load_ms: int = Field(..., ge=0)
    inference_ms: int = Field(..., ge=0)
    total_ms: int = Field(..., ge=0)
    started_at: int
    completed_at: int


class CaptchaSubmitRequest(APIModel):
    session_id: str
    task_id: str
    prediction: Optional[PredictionData] = Field(
        default=None,
        description="Only present when the segment includes the final layer; "
        "mid-pipeline contributors have no prediction",
    )
    proof_of_work: Optional[ProofOfWorkData] = None
    proof: Optional[InferenceProofData] = None
    timing: TimingData

    @model_validator(mode="after")
    def validate_proof_variant(self) -> "CaptchaSubmitRequest":
        if self.proof_of_work is None and self.proof is None:
            raise ValueError("Either proof_of_work or proof must be provided")
        return self


class VerificationDisplayData(APIModel):
    type: str
    url: Optional[str] = None
    content: Optional[str] = None


class VerificationOption(APIModel):
    id: str
    label: str
    type: str


class VerificationInfo(APIModel):
    verification_id: str
    display_data: VerificationDisplayData
    predicted_label: str
    prompt: str
    options: List[VerificationOption]


class PipelineProgressInfo(APIModel):
    """Progress of the distributed inference run the user contributed to."""

    run_id: str
    layers_done: int
    total_layers: int
    completed: bool
    predicted_label: Optional[str] = None
    confidence: Optional[float] = None
    contributors: int = 1


class CaptchaSubmitResponse(APIModel):
    success: bool
    requires_verification: bool
    verification: Optional[VerificationInfo] = None
    captcha_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    pipeline: Optional[PipelineProgressInfo] = None


class CaptchaValidateResponse(APIModel):
    valid: bool
    session_id: Optional[str] = None
    domain: Optional[str] = None
    completed_at: Optional[datetime] = None
    difficulty: Optional[str] = None
    verification_performed: Optional[bool] = None
