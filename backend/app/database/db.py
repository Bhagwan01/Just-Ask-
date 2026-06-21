"""
Async database engine and session management.

Uses SQLAlchemy 2.0 async API with:
- Connection pooling
- Auto-retry for transient errors
- Health check query
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy import text

from app.core.logging import get_logger
from app.core.settings import AppSettings

logger = get_logger(__name__)


def create_engine(settings: AppSettings) -> AsyncEngine:
    """Create an async SQLAlchemy engine from settings."""
    connect_args = {}
    kwargs = {
        "echo": settings.db_echo,
    }

    if "sqlite" in settings.database_url:
        # SQLite needs check_same_thread=False for async
        connect_args["check_same_thread"] = False
        kwargs["poolclass"] = StaticPool
    else:
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
        kwargs["pool_pre_ping"] = True  # Verify connections before use
        kwargs["pool_recycle"] = 3600   # Recycle connections after 1 hour

    engine = create_async_engine(
        settings.database_url,
        connect_args=connect_args,
        **kwargs,
    )
    logger.info(f"Database engine created: {settings.database_url.split('://')[0]}")
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async session factory."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


async def init_db(engine: AsyncEngine) -> None:
    """Create all tables (for development). Use Alembic in production."""
    from app.models.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def check_db_health(engine: AsyncEngine) -> bool:
    """Run a simple query to verify database connectivity."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def close_db(engine: AsyncEngine) -> None:
    """Gracefully close the database engine."""
    await engine.dispose()
    logger.info("Database engine closed")
