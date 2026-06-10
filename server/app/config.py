"""
PoUW CAPTCHA Server Configuration

Pydantic Settings for configuration management with environment variable support.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    debug: bool = Field(default=True, description="Debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Database - defaults to SQLite for local development
    database_url: str = Field(
        default="sqlite+aiosqlite:///./pouw_captcha.db",
        description="Database connection URL (SQLite for dev, PostgreSQL for prod)",
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Max overflow connections")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")
    redis_session_db: int = Field(default=0, description="Redis DB for sessions")
    redis_cache_db: int = Field(default=1, description="Redis DB for cache")
    redis_rate_limit_db: int = Field(default=2, description="Redis DB for rate limiting")

    # Security
    secret_key: str = Field(
        default="your-super-secret-key-change-in-production",
        description="Secret key for JWT signing",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiry_minutes: int = Field(default=5, description="JWT expiry in minutes")
    captcha_token_expiry_seconds: int = Field(
        default=300, description="CAPTCHA token expiry in seconds"
    )
    admin_api_key: Optional[str] = Field(
        default=None,
        description="Optional admin key required for site registration in production",
    )
    allow_debug_site_autocreate: bool = Field(
        default=True,
        description="Auto-create pk_demo/pk_test domains in debug mode",
    )

    # CORS
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:3001", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
        description="Allowed CORS origins",
    )
    allowed_hosts: List[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Allowed hosts",
    )

    @field_validator("allowed_origins", "allowed_hosts", mode="before")
    @classmethod
    def split_string_to_list(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",")]
        return v

    # ML Configuration
    model_cdn_url: str = Field(
        default="https://cdn.pouw.dev/models",
        description="CDN URL for ML models",
    )
    sample_cdn_url: str = Field(
        default="https://cdn.pouw.dev/samples",
        description="CDN URL for samples",
    )
    default_model: str = Field(default="mnist-tiny", description="Default model")
    inference_timeout_ms: int = Field(default=10000, description="Inference timeout")

    # Task Coordinator
    normal_difficulty_time_ms: int = Field(
        default=500, description="Normal difficulty inference time"
    )
    suspicious_difficulty_time_ms: int = Field(
        default=3000, description="Suspicious difficulty inference time"
    )
    bot_difficulty_time_ms: int = Field(
        default=10000, description="Bot difficulty inference time"
    )
    verification_rate: float = Field(
        default=0.2, description="Rate of sessions requiring verification"
    )
    known_sample_rate: float = Field(
        default=0.1, description="Rate of known sample injection"
    )

    # Reputation System
    initial_reputation: float = Field(default=1.0, description="Initial reputation score")
    max_reputation: float = Field(default=5.0, description="Maximum reputation")
    min_reputation: float = Field(default=0.0, description="Minimum reputation")
    correct_verification_bonus: float = Field(
        default=0.1, description="Bonus for correct verification"
    )
    incorrect_verification_penalty: float = Field(
        default=0.2, description="Penalty for incorrect verification"
    )

    # Golden Dataset
    min_verifications_for_consensus: int = Field(
        default=3, description="Minimum verifications for consensus"
    )
    consensus_threshold: float = Field(default=0.8, description="Consensus threshold")
    discard_threshold: float = Field(default=0.6, description="Discard threshold")

    # Economics / evaluation estimates
    estimated_compute_usd_per_billion_ops: float = Field(
        default=0.20,
        description="Rough compute-cost estimate for one billion dense ops",
    )
    estimated_label_value_usd: float = Field(
        default=0.03,
        description="Rough value estimate per human-verified label",
    )

    # Rate Limiting
    rate_limit_requests_per_minute: int = Field(
        default=60, description="Rate limit requests per minute"
    )
    rate_limit_burst: int = Field(default=10, description="Rate limit burst")

    # Federated Learning
    fl_enabled: bool = Field(default=False, description="Enable federated learning")
    fl_min_clients: int = Field(
        default=10, description="Minimum clients for aggregation"
    )
    fl_gradient_clip_norm: float = Field(default=1.0, description="Gradient clip norm")
    fl_differential_privacy_epsilon: float = Field(
        default=1.0, description="Differential privacy epsilon"
    )
    fl_noise_multiplier: float = Field(default=1.1, description="Noise multiplier")

    # AWS (Production)
    aws_region: Optional[str] = Field(default=None, description="AWS region")
    s3_bucket_models: Optional[str] = Field(default=None, description="S3 bucket for models")
    s3_bucket_samples: Optional[str] = Field(default=None, description="S3 bucket for samples")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
