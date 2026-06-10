"""Site registration and public configuration endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import get_db
from app.schemas import (
    SitePublicConfigResponse,
    SiteRegisterRequest,
    SiteRegisterResponse,
)
from app.services.site_registry import SiteRegistry, admin_key_is_valid

router = APIRouter()


@router.post("/sites/register", response_model=SiteRegisterResponse)
async def register_site(
    request: SiteRegisterRequest,
    db: AsyncSession = Depends(get_db),
    x_pouw_admin_key: str | None = Header(default=None),
):
    """
    Register a website and issue its public site key plus private secret.

    The secret is returned only once and must be kept on the website backend.
    In production this endpoint requires `X-POUW-Admin-Key`.
    """
    if not admin_key_is_valid(x_pouw_admin_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin key",
        )

    registry = SiteRegistry(db)
    config, site_key, secret_key = await registry.create_site(
        domain=request.domain,
        allowed_origins=request.allowed_origins,
        verification_rate=request.verification_rate,
        difficulty_multiplier=request.difficulty_multiplier,
    )
    await db.commit()

    return SiteRegisterResponse(
        domain=config.domain,
        site_key=site_key,
        secret_key=secret_key,
        site_key_prefix=config.site_key_prefix or "",
        allowed_origins=config.allowed_origins or [],
        verification_rate=config.verification_rate,
        difficulty_multiplier=config.difficulty_multiplier,
    )


@router.get("/sites/{site_key_prefix}", response_model=SitePublicConfigResponse)
async def get_public_site_config(
    site_key_prefix: str,
    db: AsyncSession = Depends(get_db),
):
    """Return non-secret configuration for dashboards and integration checks."""
    registry = SiteRegistry(db)
    config = await registry.public_config(site_key_prefix=site_key_prefix)
    if config is None:
        raise HTTPException(status_code=404, detail="Site not found")

    return SitePublicConfigResponse(
        domain=config.domain,
        site_key_prefix=config.site_key_prefix,
        allowed_origins=config.allowed_origins or [],
        verification_rate=config.verification_rate,
        difficulty_multiplier=config.difficulty_multiplier,
        is_active=config.is_active,
    )
