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
from app.models.base import as_utc
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
    UNIT_OF_ANALYSIS,
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
    1: "RESEARCH",
    2: "HUMAN APPROVAL",
    3: "LIMITED AUTONOMOUS PUBLISHING",
    4: "FUTURE EXPERIMENTAL ACTIONS",
}
"""What the system may do on its own at each level.

Each label names the autonomous scope, not the internal artefact. Level 1 read
"RESEARCH + DRAFT", which described a `content_drafts` row rather than a
capability, and put an implementation detail in a badge on every page. What
level 1 actually means is that research is the whole of what happens without a
person: nothing outbound moves. Whether anything can be published at all is a
separate fact, and `mode.x_stage` is where it is stated.
"""

async def describe_phase(session: SessionDep, settings: SettingsDep) -> str:
    """What the system is, right now — derived, never written down.

    This line appears on every page, so a stale version of it is the system
    misdescribing itself everywhere at once. It said "still serving the demo
    dataset" for the first eight minutes after the demo dataset was deleted,
    which is exactly the failure a hardcoded status string invites: the
    deployment changed and the sentence did not.

    So it is computed from the two facts that actually determine it — whether
    fixtures are being served, and how much real history exists. A dataset
    hours old cannot produce a conclusive result, and saying so is not modesty:
    it is the reason every result currently reads INCONCLUSIVE.
    """
    if settings.demo_mode:
        return (
            "all phases built — measuring real tokens, still serving the demo "
            "dataset while history accumulates"
        )

    earliest = await session.scalar(
        select(func.min(TokenSnapshot.observed_at)).where(TokenSnapshot.is_demo.is_(False))
    )
    if earliest is None:
        return "all phases built — researching real tokens, no measurement stored yet"

    hours = max(0, int((datetime.now(UTC) - as_utc(earliest)).total_seconds() // 3600))
    if hours < 48:
        span = f"{hours} hours" if hours != 1 else "1 hour"
        return (
            f"all phases built — researching real tokens on {span} of history, "
            "which is too little to conclude anything yet"
        )
    return f"all phases built — researching real tokens on {hours // 24} days of history"


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
        unit_of_analysis=UNIT_OF_ANALYSIS,
        horizons_hours=sorted({template.horizon_hours for template in TEMPLATES}),
        llm_in_loop=False,
        last_run_at=last_run,
    )


def _scheduler_running(request: Request) -> bool:
    """Is the loop alive, right now.

    `done()` is checked as well as existence: a task that raised out of its own
    error handling is still attached to the app and would otherwise report as
    running while collecting nothing.
    """
    from app.workers.scheduler import SCHEDULER_TASK_ATTR

    task = getattr(request.app.state, SCHEDULER_TASK_ATTR, None)
    return task is not None and not task.done()


async def describe_collection(
    request: Request, session: SessionDep, settings: SettingsDep
) -> CollectionInfo:
    """What the live collectors hold, counted apart from the fixtures."""
    # Two aggregates, not one query per token. This loaded every live token as
    # an ORM object and then ran a COUNT(*) for each one: at 1,035 tokens that
    # was 1,036 round trips, `/api/status` answered in about two seconds, and
    # every page asks for it — so the cost landed on every visit to the site.
    from app.services.chain import CHAIN_RUN_NAME, MIGRATED, PROMOTED
    from app.services.social import COLLECTOR_RUN_NAME

    per_token = (
        select(func.count().label("n"))
        .select_from(TokenSnapshot)
        .join(Token, Token.id == TokenSnapshot.token_id)
        .where(Token.is_demo.is_(False))
        .group_by(TokenSnapshot.token_id)
        .subquery()
    )
    deepest = int(await session.scalar(select(func.max(per_token.c.n))) or 0)

    by_frame = {
        source: count
        for source, count in (
            await session.execute(
                select(Token.source, func.count())
                .where(Token.is_demo.is_(False))
                .group_by(Token.source)
            )
        ).all()
    }
    by_chain = {
        str(chain): int(count)
        for chain, count in (
            await session.execute(
                select(Token.chain, func.count())
                .where(Token.is_demo.is_(False))
                .group_by(Token.chain)
            )
        ).all()
    }
    token_count = sum(by_frame.values())
    promoted = by_frame.get(PROMOTED, 0)
    migrated = by_frame.get(MIGRATED, 0)

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

    return CollectionInfo(
        live_tokens=token_count,
        tokens_promoted=promoted,
        tokens_migrated=migrated,
        # Everything that is neither frame, including the NULL the clobbered
        # rows were reset to. Derived by subtraction so the three always sum.
        tokens_unrecorded_frame=token_count - promoted - migrated,
        migrations_available=bool(
            settings.launchpad_migrations and settings.launchpad_api_url
        ),
        tokens_by_chain=by_chain,
        live_snapshots=await count_live(TokenSnapshot),
        live_posts=await count_live(SocialPost),
        deepest_history=deepest,
        needed_to_observe=settings.observation_min_snapshots,
        observing_live=not settings.demo_mode,
        scheduler_running=_scheduler_running(request),
        scheduler_interval_seconds=(
            settings.scheduler_interval_seconds if settings.scheduler_enabled else None
        ),
        last_chain_run_at=await last_run(CHAIN_RUN_NAME),
        last_x_run_at=await last_run(COLLECTOR_RUN_NAME),
        measuring_since=await session.scalar(
            select(func.min(TokenSnapshot.observed_at)).where(
                TokenSnapshot.is_demo.is_(False)
            )
        ),
        running_since=await session.scalar(
            select(func.min(SystemEvent.created_at)).where(SystemEvent.is_demo.is_(False))
        ),
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
async def status_endpoint(
    request: Request, session: SessionDep, settings: SettingsDep
) -> StatusResponse:
    return StatusResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        phase=await describe_phase(session, settings),
        state=str(await get_state(session)),
        mode=ModeInfo(
            demo_mode=settings.demo_mode,
            autonomy_level=settings.autonomy_level,
            autonomy_label=AUTONOMY_LABELS[settings.autonomy_level],
            x_mode=settings.x_mode,
            x_stage=settings.x_stage,
            wallet_execution_enabled=settings.wallet_execution_enabled,
            external_content_is_untrusted=settings.external_content_is_untrusted,
        ),
        memory=describe_memory(session, settings),
        pipeline=await describe_pipeline(session, settings),
        research=await describe_research(session, settings),
        collection=await describe_collection(request, session, settings),
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
