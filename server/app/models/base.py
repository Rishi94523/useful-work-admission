"""
Base database configuration and session management.
"""

from typing import AsyncGenerator
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# Create async engine - SQLite doesn't support pool_size/max_overflow
if settings.database_url.startswith("sqlite"):
    engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.debug,
    )

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_compat_columns(conn)
    logger.info("Database tables created")


async def _ensure_compat_columns(conn) -> None:
    """
    Best-effort schema compatibility for local/demo databases.

    This project currently uses create_all instead of versioned Alembic
    migrations. create_all does not alter existing tables, so add newly
    introduced columns when an older SQLite/Postgres dev database is present.
    """
    if settings.database_url.startswith("sqlite"):
        result = await conn.exec_driver_sql("PRAGMA table_info(domain_config)")
        existing = {row[1] for row in result.fetchall()}
        columns = {
            "site_key_prefix": "ALTER TABLE domain_config ADD COLUMN site_key_prefix VARCHAR(32)",
            "secret_key_hash": "ALTER TABLE domain_config ADD COLUMN secret_key_hash VARCHAR(64)",
            "updated_at": "ALTER TABLE domain_config ADD COLUMN updated_at DATETIME",
        }
        for name, statement in columns.items():
            if name not in existing:
                await conn.exec_driver_sql(statement)
        return

    if "postgresql" in settings.database_url:
        await conn.exec_driver_sql(
            "ALTER TABLE domain_config ADD COLUMN IF NOT EXISTS site_key_prefix VARCHAR(32)"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE domain_config ADD COLUMN IF NOT EXISTS secret_key_hash VARCHAR(64)"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE domain_config ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"
        )


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    logger.info("Database connections closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for dependency injection."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
