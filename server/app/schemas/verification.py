"""
Verification API schemas.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import Field

from app.schemas.captcha import APIModel


class VerificationSubmitRequest(APIModel):
    """Request to submit human verification."""

    session_id: str = Field(..., description="Session ID")
    verification_id: str = Field(..., description="Verification ID")
    response: Literal["confirm", "correct"] = Field(
        ..., description="Response type: confirm or correct"
    )
    corrected_label: Optional[str] = Field(
        default=None, description="Corrected label if response is 'correct'"
    )
    response_time_ms: Optional[int] = Field(
        default=None, ge=0, description="Time taken to respond"
    )


class VerificationSubmitResponse(APIModel):
    """Response from verification submission."""

    success: bool = Field(..., description="Verification success")
    captcha_token: str = Field(..., description="CAPTCHA token")
    expires_at: datetime = Field(..., description="Token expiry time")


class VerificationData(APIModel):
    """Data for creating a verification request."""

    verification_id: str
    display_type: str
    display_content: str
    predicted_label: str
    prompt: str
