"""Site registration and configuration schemas."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class SiteAPIModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class SiteRegisterRequest(SiteAPIModel):
    domain: str = Field(..., min_length=3, max_length=255)
    allowed_origins: Optional[List[str]] = Field(default=None)
    verification_rate: float = Field(default=0.2, ge=0.0, le=1.0)
    difficulty_multiplier: float = Field(default=1.0, ge=0.1, le=10.0)

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return value.strip().lower()


class SiteRegisterResponse(SiteAPIModel):
    domain: str
    site_key: str
    secret_key: str
    site_key_prefix: str
    allowed_origins: List[str]
    verification_rate: float
    difficulty_multiplier: float


class SitePublicConfigResponse(SiteAPIModel):
    domain: str
    site_key_prefix: Optional[str]
    allowed_origins: List[str]
    verification_rate: float
    difficulty_multiplier: float
    is_active: bool
