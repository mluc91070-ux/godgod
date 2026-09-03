"""Observations, hypotheses, experiments, traces and patterns."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    AdminDep,
    PageDep,
    SessionDep,
    SettingsDep,
    build_page,
    count_query,
)
from app.models import (
    Experiment,
    ExperimentResult,
    Hypothesis,
    Observation,
    Pattern,
    ResearchTrace,
)
from app.schemas.common import Page
from app.schemas.research import (
    ExperimentDetail,
    ExperimentOut,
    ExperimentResultOut,
    HypothesisDetail,
    HypothesisOut,
    ObservationDetail,
    ObservationOut,
    PatternOut,
    ResearchReportOut,
    TraceOut,
)
from app.services.coverage import build_coverage
from app.services.research import run_research_cycle

router = APIRouter(prefix="/api", tags=["research"])


@router.get("/field-coverage")
async def field_coverage(session: SessionDep) -> dict:
    """How many live measurements carry a value for each snapshot field.

    The grading half of a posed thesis. An argument about a mechanism names the
    fields its steps would need; this says whether those fields hold anything,
    and it has to be the database that says it rather than the argument.

    The argument itself is static and ships with the page, because a paragraph
    somebody wrote does not become truer because a backend answered. Putting it
    behind this endpoint only meant it vanished whenever the endpoint did.
    """
    return await build_coverage(session)


@router.post("/admin/research/run", response_model=ResearchReportOut)
async def run_cycle(
    session: SessionDep, settings: SettingsDep, admin: AdminDep
) -> ResearchReportOut:
    """Generate hypotheses from anomalies, test them, and let the critic rule.

    Deterministic: templates, thresholds and statistics. `llm_calls` is 0.
    """
    report = await run_research_cycle(session, settings=settings)
    return ResearchReportOut(**report.as_dict())


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


@router.get("/results", response_model=Page[ExperimentResultOut])
async def list_results(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    outcome: str | None = Query(default=None),
    critic_verdict: str | None = Query(default=None),
) -> Page:
    """Every recorded result, rejections included.

    A result is never withdrawn because it was disappointing; filtering is the
    reader's choice, not the system's.
    """
    stmt = select(ExperimentResult).order_by(ExperimentResult.created_at.desc())
    if outcome:
        stmt = stmt.where(ExperimentResult.outcome == outcome.upper())
    if critic_verdict:
        stmt = stmt.where(ExperimentResult.critic_verdict == critic_verdict.upper())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, ExperimentResultOut, total, page, settings)


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
