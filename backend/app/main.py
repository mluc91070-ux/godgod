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

    if settings.demo_mode and os.getenv("GODGOD_AUTO_OBSERVE", "1") == "1":
        # Replay the synthetic series once so the demo shows observations the
        # pipeline actually produced, rather than hand-written ones.
        from sqlalchemy import func, select

        from app.models import AgentRun
        from app.services.observation import run_backfill
        from app.services.observation.pipeline import PIPELINE_RUN_NAME

        async with get_sessionmaker()() as session:
            already = await session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.agent_name == PIPELINE_RUN_NAME)
            )
            if not already:
                reports = await run_backfill(session, settings=settings)
                logger.info(
                    "observation backfill: %s cycles, %s observations, %s anomalies",
                    len(reports),
                    sum(report.observations_created for report in reports),
                    sum(report.anomalies_created for report in reports),
                )

    if settings.demo_mode and os.getenv("GODGOD_AUTO_RESEARCH", "1") == "1":
        # Turn the anomalies the pipeline just found into questions, and test
        # them. Skipped if a cycle has already run against this database.
        from sqlalchemy import func, select

        from app.models import AgentRun
        from app.services.research import RESEARCH_RUN_NAME, run_research_cycle

        async with get_sessionmaker()() as session:
            already = await session.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(AgentRun.agent_name == RESEARCH_RUN_NAME)
            )
            if not already:
                report = await run_research_cycle(session, settings=settings)
                logger.info("research cycle: %s", report.as_dict())

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
