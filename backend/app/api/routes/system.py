"""Health, status, live snapshot, events, metrics, agents and sources."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select, text

from app.api.deps import PageDep, SessionDep, SettingsDep, build_page, count_query
from app.core.enums import ExperimentStatus, HypothesisStatus, ResultOutcome
from app.models import (
    Agent,
    AgentRun,
    ExperimentResult,
    Hypothesis,
    MetricsSnapshot,
    ResearchSource,
    SystemEvent,
)
from app.providers.registry import describe_providers
from app.schemas.common import (
    HealthResponse,
    LiveResponse,
    MemoryInfo,
    ModeInfo,
    Page,
    StatusResponse,
)
from app.schemas.research import AgentOut, AgentRunOut, EventOut, MetricsResponse, SourceOut
from app.services.embeddings import get_embedding_provider
from app.services.memory import dialect_name
from app.services.state import get_counts, get_live, get_state


def describe_memory(session: SessionDep, settings: SettingsDep) -> MemoryInfo:
    provider = get_embedding_provider(settings)
    vector_search = settings.embedding_provider != "none"
    return MemoryInfo(
        embedding_provider=settings.embedding_provider,
        embedding_model=provider.name if vector_search else None,
        embedding_dim=provider.dim,
        vector_search=vector_search,
        semantic=provider.semantic,
        backend="pgvector" if dialect_name(session) == "postgresql" else "python-scan",
    )

router = APIRouter(tags=["system"])

AUTONOMY_LABELS = {
    0: "READ ONLY",
    1: "RESEARCH + DRAFT",
    2: "HUMAN APPROVAL + PUBLISH",
    3: "LIMITED AUTONOMOUS PUBLISHING",
    4: "FUTURE EXPERIMENTAL ACTIONS",
}

CURRENT_PHASE = "PHASE 2 — memory (store, embed, rank, cluster, digest)"


@router.get("/health", response_model=HealthResponse, include_in_schema=True)
async def health(session: SessionDep, settings: SettingsDep) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:
        database = f"error: {type(exc).__name__}"
    return HealthResponse(status="ok", version=settings.app_version, database=database)


@router.get("/api/status", response_model=StatusResponse)
async def status_endpoint(session: SessionDep, settings: SettingsDep) -> StatusResponse:
    return StatusResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        phase=CURRENT_PHASE,
        state=str(await get_state(session)),
        mode=ModeInfo(
            demo_mode=settings.demo_mode,
            autonomy_level=settings.autonomy_level,
            autonomy_label=AUTONOMY_LABELS[settings.autonomy_level],
            x_mode=settings.x_mode,
            wallet_execution_enabled=settings.wallet_execution_enabled,
            external_content_is_untrusted=settings.external_content_is_untrusted,
        ),
        memory=describe_memory(session, settings),
        providers=describe_providers(settings),
        counts=await get_counts(session),
        server_time=datetime.now(UTC),
    )


@router.get("/api/live", response_model=LiveResponse)
async def live(session: SessionDep) -> LiveResponse:
    return await get_live(session)


@router.get("/api/events", response_model=Page[EventOut])
async def list_events(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    event_type: str | None = Query(default=None),
) -> Page:
    stmt = select(SystemEvent).order_by(SystemEvent.occurred_at.desc())
    if event_type:
        stmt = stmt.where(SystemEvent.event_type == event_type)
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, EventOut, total, page, settings)


@router.get("/api/metrics", response_model=MetricsResponse)
async def metrics(session: SessionDep, settings: SettingsDep) -> MetricsResponse:
    counts = await get_counts(session)
    snapshot = await session.scalar(
        select(MetricsSnapshot).order_by(MetricsSnapshot.captured_at.desc()).limit(1)
    )

    outcomes: dict[str, int] = {}
    for outcome in ResultOutcome:
        stmt = select(ExperimentResult).where(ExperimentResult.outcome == str(outcome))
        outcomes[str(outcome).lower()] = await count_query(session, stmt)

    statuses: dict[str, int] = {}
    for hypothesis_status in HypothesisStatus:
        stmt = select(Hypothesis).where(Hypothesis.status == str(hypothesis_status))
        statuses[str(hypothesis_status).lower()] = await count_query(session, stmt)

    cost = await session.scalar(select(func.sum(AgentRun.estimated_cost_usd)))

    return MetricsResponse(
        window=snapshot.window if snapshot else "all-time",
        captured_at=snapshot.captured_at if snapshot else None,
        counts={
            **counts.model_dump(),
            "results_by_outcome": outcomes,
            "hypotheses_by_status": statuses,
            "experiment_statuses": [str(item) for item in ExperimentStatus],
        },
        llm_cost_usd=cost,
        is_demo=settings.demo_mode,
    )


@router.get("/api/agents", response_model=list[AgentOut])
async def list_agents(session: SessionDep) -> list[Agent]:
    return list((await session.scalars(select(Agent).order_by(Agent.name))).all())


@router.get("/api/agents/runs", response_model=Page[AgentRunOut])
async def list_agent_runs(session: SessionDep, settings: SettingsDep, page: PageDep) -> Page:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, AgentRunOut, total, page, settings)


@router.get("/api/sources", response_model=list[SourceOut])
async def list_sources(session: SessionDep) -> list[ResearchSource]:
    return list((await session.scalars(select(ResearchSource).order_by(ResearchSource.name))).all())
