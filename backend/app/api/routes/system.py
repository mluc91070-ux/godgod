"""Health, status, live snapshot, events, metrics, agents and sources."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse
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
    SocialPost,
    SystemEvent,
    Token,
    TokenSnapshot,
)
from app.providers.registry import describe_providers
from app.providers.source import get_observation_source
from app.schemas.common import (
    CollectionInfo,
    HealthResponse,
    LiveResponse,
    MemoryInfo,
    ModeInfo,
    Page,
    PipelineInfo,
    ResearchInfo,
    StatusResponse,
)
from app.schemas.research import AgentOut, AgentRunOut, EventOut, MetricsResponse, SourceOut
from app.services.embeddings import get_embedding_provider
from app.services.memory import dialect_name
from app.services.observation.detectors import DETECTOR_NAMES
from app.services.observation.pipeline import PIPELINE_RUN_NAME
from app.services.research import (
    CHECK_NAMES,
    CRITIC_VERSION,
    MIN_CELL,
    RESEARCH_RUN_NAME,
    TEMPLATES,
)
from app.services.state import get_counts, get_live, get_state
from app.services.stream import STREAM_VERSION, event_stream


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

CURRENT_PHASE = (
    "all phases built — observing real tokens, still serving the demo dataset "
    "while history accumulates"
)
"""What the system is, right now.

Not a phase number: every phase is built, and a stale "PHASE 6" here would be
the system misdescribing itself on every page — which is the one thing it is
not allowed to do. Change this when the deployment changes, not when a
milestone is passed.
"""


async def describe_pipeline(session: SessionDep, settings: SettingsDep) -> PipelineInfo:
    source = get_observation_source(session=session, settings=settings)
    last_run = await session.scalar(
        select(func.max(AgentRun.started_at)).where(AgentRun.agent_name == PIPELINE_RUN_NAME)
    )
    return PipelineInfo(
        implemented=True,
        source=source.name,
        source_is_demo=source.is_demo,
        window_hours=settings.observation_window_hours,
        detectors=sorted(DETECTOR_NAMES),
        llm_in_loop=False,
        last_run_at=last_run,
    )


async def describe_research(session: SessionDep, settings: SettingsDep) -> ResearchInfo:
    last_run = await session.scalar(
        select(func.max(AgentRun.started_at)).where(AgentRun.agent_name == RESEARCH_RUN_NAME)
    )
    return ResearchInfo(
        implemented=True,
        hypothesis_templates=len(TEMPLATES),
        critic_version=CRITIC_VERSION,
        critic_checks=list(CHECK_NAMES),
        min_group_size=MIN_CELL,
        unit_of_analysis="token-hour",
        llm_in_loop=False,
        last_run_at=last_run,
    )


async def describe_collection(session: SessionDep, settings: SettingsDep) -> CollectionInfo:
    """What the live collectors hold, counted apart from the fixtures."""
    from app.services.chain import CHAIN_RUN_NAME
    from app.services.social import COLLECTOR_RUN_NAME

    live_tokens = (await session.scalars(select(Token).where(Token.is_demo.is_(False)))).all()

    deepest = 0
    for token in live_tokens:
        count = int(
            await session.scalar(
                select(func.count())
                .select_from(TokenSnapshot)
                .where(TokenSnapshot.token_id == token.id)
            )
            or 0
        )
        deepest = max(deepest, count)

    async def count_live(model) -> int:
        return int(
            await session.scalar(
                select(func.count()).select_from(model).where(model.is_demo.is_(False))
            )
            or 0
        )

    async def last_run(name: str) -> datetime | None:
        return await session.scalar(
            select(func.max(AgentRun.started_at)).where(AgentRun.agent_name == name)
        )

    from app.services.chain import MIGRATED, PROMOTED

    return CollectionInfo(
        live_tokens=len(live_tokens),
        tokens_promoted=sum(1 for token in live_tokens if token.source == PROMOTED),
        tokens_migrated=sum(1 for token in live_tokens if token.source == MIGRATED),
        migrations_available=bool(
            settings.launchpad_migrations and settings.launchpad_api_url
        ),
        live_snapshots=await count_live(TokenSnapshot),
        live_posts=await count_live(SocialPost),
        deepest_history=deepest,
        needed_to_observe=settings.observation_min_snapshots,
        observing_live=not settings.demo_mode,
        last_chain_run_at=await last_run(CHAIN_RUN_NAME),
        last_x_run_at=await last_run(COLLECTOR_RUN_NAME),
    )


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
        pipeline=await describe_pipeline(session, settings),
        research=await describe_research(session, settings),
        collection=await describe_collection(session, settings),
        providers=describe_providers(settings),
        counts=await get_counts(session),
        server_time=datetime.now(UTC),
    )


@router.get("/api/live", response_model=LiveResponse)
async def live(session: SessionDep) -> LiveResponse:
    return await get_live(session)


@router.get("/api/live/stream")
async def live_stream(
    request: Request,
    settings: SettingsDep,
    after: int | None = Query(
        default=None,
        ge=0,
        description="Resume from this system_events.seq. Omit to replay the recent tail.",
    ),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    """Server-sent events over the log the system writes as it works.

    Frames: `open` (cursor and what this connection will do), `log` (one event
    row, `replayed` true for history), `state` (derived state changed), `close`
    (this connection is ageing out; reconnect with the cursor). A `:` comment
    every few seconds is the heartbeat.

    The browser resends `Last-Event-ID` automatically on reconnect, so no event
    is skipped and none is delivered twice.
    """
    cursor = after
    if cursor is None and last_event_id and last_event_id.isdigit():
        cursor = int(last_event_id)

    return StreamingResponse(
        event_stream(settings, after=cursor, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Stream-Version": STREAM_VERSION,
        },
    )


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
