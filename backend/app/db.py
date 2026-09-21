"""Async SQLAlchemy engine and session management."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(url: str | None = None, **kwargs) -> AsyncEngine:
    """(Re)initialize the global engine and session factory."""
    global _engine, _session_factory
    settings = get_settings()
    engine = create_async_engine(url or settings.database_url, **kwargs)
    _engine = engine
    _session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine


def get_engine() -> AsyncEngine:
    return _engine or init_engine()


def new_session() -> AsyncSession:
    global _session_factory
    if _session_factory is None:
        init_engine()
    return _session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped session."""
    async with new_session() as session:
        yield session
