"""Observations, hypotheses, experiments, traces and patterns."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import PageDep, SessionDep, SettingsDep, build_page, count_query
from app.models import (
    Experiment,
    Hypothesis,
    Observation,
    Pattern,
    ResearchTrace,
)
from app.schemas.common import Page
from app.schemas.research import (
    ExperimentDetail,
    ExperimentOut,
    HypothesisDetail,
    HypothesisOut,
    ObservationDetail,
    ObservationOut,
    PatternOut,
    TraceOut,
)

router = APIRouter(prefix="/api", tags=["research"])


@router.get("/observations", response_model=Page[ObservationOut])
async def list_observations(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    kind: str | None = Query(default=None),
    min_novelty: float | None = Query(default=None, ge=0.0, le=1.0),
    subject_ref: str | None = Query(default=None),
) -> Page:
    stmt = select(Observation).order_by(Observation.observed_at.desc())
    if kind:
        stmt = stmt.where(Observation.kind == kind)
    if min_novelty is not None:
        stmt = stmt.where(Observation.novelty_score >= min_novelty)
    if subject_ref:
        stmt = stmt.where(Observation.subject_ref == subject_ref)
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, ObservationOut, total, page, settings)


@router.get("/observations/{observation_id}", response_model=ObservationDetail)
async def get_observation(session: SessionDep, observation_id: str) -> Observation:
    row = await session.scalar(
        select(Observation)
        .options(selectinload(Observation.anomalies))
        .where(Observation.id == observation_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="observation not found")
    return row


@router.get("/hypotheses", response_model=Page[HypothesisOut])
async def list_hypotheses(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> Page:
    stmt = select(Hypothesis).order_by(Hypothesis.created_at.desc())
    if status_filter:
        stmt = stmt.where(Hypothesis.status == status_filter.upper())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, HypothesisOut, total, page, settings)


@router.get("/hypotheses/{hypothesis_id}", response_model=HypothesisDetail)
async def get_hypothesis(session: SessionDep, hypothesis_id: str) -> Hypothesis:
    row = await session.scalar(
        select(Hypothesis)
        .options(selectinload(Hypothesis.experiments))
        .where(Hypothesis.id == hypothesis_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="hypothesis not found")
    return row


@router.get("/experiments", response_model=Page[ExperimentOut])
async def list_experiments(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> Page:
    stmt = select(Experiment).order_by(Experiment.created_at.desc())
    if status_filter:
        stmt = stmt.where(Experiment.status == status_filter.upper())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, ExperimentOut, total, page, settings)


@router.get("/experiments/{experiment_id}", response_model=ExperimentDetail)
async def get_experiment(session: SessionDep, experiment_id: str) -> Experiment:
    row = await session.scalar(
        select(Experiment)
        .options(selectinload(Experiment.results), selectinload(Experiment.hypothesis))
        .where(Experiment.id == experiment_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return row


@router.get("/traces", response_model=Page[TraceOut])
async def list_traces(session: SessionDep, settings: SettingsDep, page: PageDep) -> Page:
    stmt = (
        select(ResearchTrace)
        .options(selectinload(ResearchTrace.steps))
        .order_by(ResearchTrace.started_at.desc())
    )
    total = await count_query(session, select(ResearchTrace))
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, TraceOut, total, page, settings)


@router.get("/traces/{trace_id}", response_model=TraceOut)
async def get_trace(session: SessionDep, trace_id: str) -> ResearchTrace:
    row = await session.scalar(
        select(ResearchTrace)
        .options(selectinload(ResearchTrace.steps))
        .where(ResearchTrace.id == trace_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return row


@router.get("/patterns", response_model=Page[PatternOut])
async def list_patterns(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> Page:
    stmt = select(Pattern).order_by(Pattern.created_at.desc())
    if status_filter:
        stmt = stmt.where(Pattern.status == status_filter.upper())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, PatternOut, total, page, settings)
