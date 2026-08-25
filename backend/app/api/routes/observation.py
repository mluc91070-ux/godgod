"""Anomalies and the observation pipeline trigger."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminDep, PageDep, SessionDep, SettingsDep, build_page, count_query
from app.models import Anomaly
from app.schemas.common import Page
from app.schemas.research import AnomalyOut, RunReportOut
from app.services.observation import ObservationPipeline, run_backfill

router = APIRouter(prefix="/api", tags=["observation"])


@router.get("/anomalies", response_model=Page[AnomalyOut])
async def list_anomalies(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    anomaly_type: str | None = Query(default=None, alias="type"),
    min_score: float | None = Query(default=None, ge=0.0, le=1.0),
) -> Page:
    stmt = select(Anomaly).options(selectinload(Anomaly.observation)).order_by(
        Anomaly.detected_at.desc()
    )
    if anomaly_type:
        stmt = stmt.where(Anomaly.anomaly_type == anomaly_type.upper())
    if min_score is not None:
        stmt = stmt.where(Anomaly.score >= min_score)
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, AnomalyOut, total, page, settings)


@router.post("/admin/observe/run", response_model=RunReportOut)
async def run_observation_cycle(
    session: SessionDep,
    settings: SettingsDep,
    admin: AdminDep,
    mode: Literal["cycle", "backfill"] = Query(default="cycle"),
) -> RunReportOut:
    """Run the deterministic pipeline. No model is called; `llm_calls` is 0."""
    if mode == "backfill":
        reports = await run_backfill(session, settings=settings)
        merged = RunReportOut(
            as_of=reports[-1].as_of if reports else None,
            cycles=len(reports),
            subjects_examined=sum(r.subjects_examined for r in reports),
            dropped={
                key: sum(r.dropped.get(key, 0) for r in reports)
                for key in {k for r in reports for k in r.dropped}
            },
            observations_created=sum(r.observations_created for r in reports),
            anomalies_created=sum(r.anomalies_created for r in reports),
            memories_written=sum(r.memories_written for r in reports),
            events_emitted=sum(r.events_emitted for r in reports),
            snapshots_ingested=sum(r.snapshots_ingested for r in reports),
            posts_ingested=sum(r.posts_ingested for r in reports),
            duration_ms=sum(r.duration_ms for r in reports),
            llm_calls=0,
        )
        return merged

    report = await ObservationPipeline(settings=settings).run(session)
    return RunReportOut(cycles=1, **report.as_dict())
