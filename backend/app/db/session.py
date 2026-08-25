"""Async engine and session management.

Local development and tests run on SQLite (aiosqlite). Production runs on
PostgreSQL + pgvector via ``postgresql+psycopg``. The URL is the only
difference; no code branches on the backend except in db/types.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _normalize_url(url: str) -> str:
    """Accept sync-style URLs and upgrade them to their async drivers."""
    if url.startswith("sqlite+pysqlite:"):
        return url.replace("sqlite+pysqlite:", "sqlite+aiosqlite:", 1)
    if url.startswith("sqlite:"):
        return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def build_engine(settings: Settings | None = None, **kwargs: Any) -> AsyncEngine:
    settings = settings or get_settings()
    url = _normalize_url(settings.database_url)
    options: dict[str, Any] = {"echo": settings.database_echo, "future": True}
    if not url.startswith("sqlite"):
        options |= {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5}
    options |= kwargs
    return create_async_engine(url, **options)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = build_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with get_sessionmaker()() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
