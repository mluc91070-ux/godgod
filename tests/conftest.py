"""Test harness.

Every test gets its own SQLite database, freshly created and seeded from the
repository fixtures, so state-changing tests cannot leak into each other.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ADMIN_TOKEN = "test-admin-token"


@pytest_asyncio.fixture
async def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "godgod-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("GODGOD_AUTO_SEED", "0")

    from app.core.config import get_settings
    from app.db.session import dispose_engine

    get_settings.cache_clear()
    await dispose_engine()

    yield get_settings()

    await dispose_engine()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def session(settings) -> AsyncIterator:
    from app.db.session import get_engine, get_sessionmaker
    from app.models import Base

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def seeded(session):
    from app.services.seed import seed_demo

    counts = await seed_demo(session, force=True)
    return counts


@pytest_asyncio.fixture
async def client(seeded) -> AsyncIterator[AsyncClient]:
    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN}
