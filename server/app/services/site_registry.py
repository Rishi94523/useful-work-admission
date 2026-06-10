"""Site key registration, lookup, and domain/origin enforcement."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import DomainConfig
from app.utils.security import (
    generate_api_key,
    generate_secret_key,
    hash_api_key,
    key_prefix,
    verify_api_key,
)

settings = get_settings()


class SiteRegistryError(ValueError):
    """Raised when a site key, domain, or origin is not allowed."""


@dataclass(frozen=True)
class RegisteredSite:
    config: DomainConfig
    site_key_prefix: str


def normalize_domain(value: str) -> str:
    """Normalize a domain, origin, or URL to a lowercase hostname."""
    value = value.strip().lower()
    if "://" in value:
        parsed = urlparse(value)
        return parsed.hostname or value
    return value.split("/")[0].split(":")[0]


def normalize_origin(value: str) -> str:
    """Normalize origin strings to scheme://host[:port] where possible."""
    value = value.strip().lower().rstrip("/")
    parsed = urlparse(value if "://" in value else f"https://{value}")
    if not parsed.hostname:
        return value
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def extract_origin(origin: Optional[str], referer: Optional[str]) -> Optional[str]:
    """Get the best request origin signal from Origin or Referer."""
    candidate = origin or referer
    if not candidate:
        return None
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.hostname:
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{port}"
    return normalize_origin(candidate)


def origin_host(origin: Optional[str]) -> Optional[str]:
    if not origin:
        return None
    return urlparse(origin).hostname or normalize_domain(origin)


def is_origin_allowed(domain: str, allowed_origins: Optional[Iterable[str]], origin: Optional[str]) -> bool:
    """Check whether a request origin is permitted for a registered site."""
    if not origin:
        return settings.debug

    normalized_request = normalize_origin(origin)
    request_host = origin_host(normalized_request)
    domain_host = normalize_domain(domain)

    if request_host == domain_host:
        return True

    if settings.debug and request_host in {"localhost", "127.0.0.1"}:
        return True

    for allowed in allowed_origins or []:
        if allowed == "*":
            return True
        normalized_allowed = normalize_origin(allowed)
        allowed_host = origin_host(normalized_allowed)
        if normalized_allowed == normalized_request or allowed_host == request_host:
            return True

    return False


class SiteRegistry:
    """Registry for public site keys and private validation secrets."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_site(
        self,
        *,
        domain: str,
        allowed_origins: Optional[list[str]] = None,
        verification_rate: float = 0.2,
        difficulty_multiplier: float = 1.0,
        site_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ) -> tuple[DomainConfig, str, str]:
        """Create a site registration and return plaintext keys once."""
        site_key = site_key or generate_api_key()
        secret_key = secret_key or generate_secret_key()
        normalized_domain = normalize_domain(domain)
        normalized_origins = [
            normalize_origin(origin)
            for origin in (allowed_origins or [f"https://{normalized_domain}"])
        ]

        config = DomainConfig(
            domain=normalized_domain,
            api_key_hash=hash_api_key(site_key),
            site_key_prefix=key_prefix(site_key),
            secret_key_hash=hash_api_key(secret_key),
            allowed_origins=normalized_origins,
            verification_rate=verification_rate,
            difficulty_multiplier=difficulty_multiplier,
            is_active=True,
        )
        self.db.add(config)
        await self.db.flush()
        return config, site_key, secret_key

    async def resolve_site(
        self,
        *,
        site_key: str,
        origin: Optional[str] = None,
        referer: Optional[str] = None,
    ) -> RegisteredSite:
        """Resolve and validate a public site key for a browser request."""
        config = await self._get_by_site_key(site_key)
        request_origin = extract_origin(origin, referer)

        if config is None and self._can_autocreate_debug_key(site_key):
            domain = origin_host(request_origin) or "localhost"
            config, _, _ = await self.create_site(
                domain=domain,
                allowed_origins=[request_origin or "http://localhost:3000"],
                site_key=site_key,
                secret_key=generate_secret_key(prefix="sk_test"),
            )

        if config is None:
            raise SiteRegistryError("unknown site key")
        if not config.is_active:
            raise SiteRegistryError("site key is inactive")
        if not is_origin_allowed(config.domain, config.allowed_origins, request_origin):
            raise SiteRegistryError("origin is not allowed for this site key")

        return RegisteredSite(config=config, site_key_prefix=config.site_key_prefix or key_prefix(site_key))

    async def validate_secret_for_domain(self, *, domain: str, secret_key: str) -> bool:
        """Validate a private secret key for server-to-server token checks."""
        result = await self.db.execute(
            select(DomainConfig).where(
                DomainConfig.domain == normalize_domain(domain),
                DomainConfig.is_active.is_(True),
            )
        )
        config = result.scalar_one_or_none()
        if not config or not config.secret_key_hash:
            return False
        return verify_api_key(secret_key, config.secret_key_hash)

    async def public_config(self, *, site_key_prefix: str) -> Optional[DomainConfig]:
        result = await self.db.execute(
            select(DomainConfig).where(DomainConfig.site_key_prefix == site_key_prefix)
        )
        return result.scalar_one_or_none()

    async def _get_by_site_key(self, site_key: str) -> Optional[DomainConfig]:
        result = await self.db.execute(
            select(DomainConfig).where(DomainConfig.api_key_hash == hash_api_key(site_key))
        )
        return result.scalar_one_or_none()

    def _can_autocreate_debug_key(self, site_key: str) -> bool:
        if not settings.debug or not settings.allow_debug_site_autocreate:
            return False
        return site_key.startswith("pk_demo_") or site_key.startswith("pk_test_")


def admin_key_is_valid(provided: Optional[str]) -> bool:
    """Validate optional admin key for management endpoints."""
    if not settings.admin_api_key:
        return settings.debug
    if not provided:
        return False
    return hmac.compare_digest(provided, settings.admin_api_key)
