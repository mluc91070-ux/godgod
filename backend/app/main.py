"""GODGOD API entrypoint."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.models import Base

logger = logging.getLogger("godgod")

DESCRIPTION = (
    "GODGOD is an autonomous meme-research system. This API exposes what the "
    "system has actually observed, hypothesised, tested and rejected. Missing "
    "measurements are returned as null; they are never filled in with guesses."
)


async def _create_schema_for_sqlite() -> None:
    """SQLite dev/test convenience. PostgreSQL schema comes from Alembic."""
    engine = get_engine()
    if engine.url.get_backend_name() != "sqlite":
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await _create_schema_for_sqlite()

    if settings.demo_mode and os.getenv("GODGOD_AUTO_SEED", "1") == "1":
        from app.services.seed import seed_demo

        async with get_sessionmaker()() as session:
            result = await seed_demo(session)
        logger.info("demo seed: %s", result)

    logger.info(
        "GODGOD %s starting | demo=%s autonomy=%s x_mode=%s",
        settings.app_version,
        settings.demo_mode,
        settings.autonomy_level,
        settings.x_mode,
    )
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/", tags=["system"])
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "role": "autonomous meme researcher",
            "version": settings.app_version,
            "demo_mode": settings.demo_mode,
            "docs": "/docs",
        }

    return app


app = create_app()
