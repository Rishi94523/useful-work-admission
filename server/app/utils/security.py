"""
Security utilities for JWT and token management.
"""

import logging
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_jwt_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT token.

    Args:
        data: Payload data
        expires_delta: Token expiry duration

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiry_minutes)

    to_encode.update({"exp": expire, "iat": datetime.utcnow()})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return encoded_jwt


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def generate_captcha_token(
    session_id: str,
    domain: str,
    site_key_prefix: Optional[str] = None,
    action: Optional[str] = None,
    work_units: Optional[int] = None,
) -> str:
    """
    Generate a CAPTCHA completion token.

    Args:
        session_id: Session UUID
        domain: Domain that requested the CAPTCHA

    Returns:
        JWT token for CAPTCHA verification
    """
    return create_jwt_token(
        data={
            "type": "captcha_token",
            "jti": str(uuid.uuid4()),
            "session_id": session_id,
            "domain": domain,
            "completed_at": datetime.utcnow().isoformat(),
            "site_key_prefix": site_key_prefix,
            "action": action,
            "work_units": work_units,
        },
        expires_delta=timedelta(seconds=settings.captcha_token_expiry_seconds),
    )


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for storage.

    Args:
        api_key: Plain text API key

    Returns:
        Hashed API key
    """
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """
    Verify an API key against its hash.

    Args:
        plain_key: Plain text API key
        hashed_key: Hashed API key

    Returns:
        True if valid
    """
    expected = hash_api_key(plain_key)
    if len(hashed_key) == 64:
        return hmac.compare_digest(expected, hashed_key)

    # Backward-compatible fallback for any legacy bcrypt-hashed keys.
    try:
        return pwd_context.verify(plain_key, hashed_key)
    except Exception:
        return False


def generate_api_key(prefix: str = "pk_live") -> str:
    """Generate a new public site key."""
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def generate_secret_key(prefix: str = "sk_live") -> str:
    """Generate a new server-side validation secret."""
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def key_prefix(api_key: str) -> str:
    """Return a non-secret prefix suitable for logs and dashboards."""
    parts = api_key.split("_", 2)
    if len(parts) >= 3:
        return f"{parts[0]}_{parts[1]}_{parts[2][:8]}"
    return api_key[:16]
