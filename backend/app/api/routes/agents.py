"""Running the model-backed agents, and reporting what they cost.

Every endpoint here spends money, so every one requires the operator token and
every one reports what it spent. A run that made no call because the budget
refused it is a 200 with `ok: false` and the reason — not a silent no-op.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.agents import critique_result, read_anomaly, review_draft, write_draft_for_result
from app.api.deps import AdminDep, SessionDep, SettingsDep
from app.models import Anomaly, ContentDraft, ExperimentResult, Token, TokenSnapshot
from app.schemas.agents import (
    BudgetOut,
    ChainOut,
    CollectionOut,
    CriticOut,
    GoLiveOut,
    ObserverOut,
    ReviewOut,
    WriterOut,
)
from app.services.budget import get_budget_status
from app.services.chain import collect_chain
from app.services.social import collect_posts

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/budget", response_model=BudgetOut)
async def budget(session: SessionDep, settings: SettingsDep) -> BudgetOut:
    """Today's model spend, from the same rows /api/metrics publishes."""
    status = await get_budget_status(session, settings=settings)
    return BudgetOut(**status.as_dict())


@router.post("/admin/agents/writer/run", response_model=WriterOut)
async def run_writer(
    session: SessionDep, settings: SettingsDep, admin: AdminDep, result_id: str
) -> WriterOut:
    """Draft one post about one recorded result.

    The draft is stored only if every number in it appears in that result. A
    refusal returns the reasons and stores nothing.
    """
    exists = await session.scalar(
        select(ExperimentResult.id).where(ExperimentResult.id == result_id)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="result not found")

    outcome = await write_draft_for_result(session, result_id, settings=settings)
    return WriterOut(**outcome.as_dict())


@router.post("/admin/agents/reviewer/run", response_model=ReviewOut)
async def run_reviewer(
    session: SessionDep, settings: SettingsDep, admin: AdminDep, draft_id: str
) -> ReviewOut:
    """Check one draft against the row it claims to describe.

    The deterministic checks always run; the model reading only happens if they
    pass. An approval here is a verdict, never a publish.
    """
    exists = await session.scalar(select(ContentDraft.id).where(ContentDraft.id == draft_id))
    if exists is None:
        raise HTTPException(status_code=404, detail="draft not found")

    outcome = await review_draft(session, draft_id, settings=settings)
    return ReviewOut(**outcome.as_dict())


@router.post("/admin/agents/critic/run", response_model=CriticOut)
async def run_critic(
    session: SessionDep, settings: SettingsDep, admin: AdminDep, result_id: str
) -> CriticOut:
    """Ask the model why one recorded result might be wrong.

    The deterministic verdict is already stored and is the floor: this can make
    it harsher and cannot make it lighter. A model answer that tries to is
    recorded under `dropped` rather than applied.
    """
    exists = await session.scalar(
        select(ExperimentResult.id).where(ExperimentResult.id == result_id)
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="result not found")

    outcome = await critique_result(session, result_id, settings=settings)
    return CriticOut(**outcome.as_dict())


@router.post("/admin/agents/observer/run", response_model=ObserverOut)
async def run_observer(
    session: SessionDep, settings: SettingsDep, admin: AdminDep, anomaly_id: str
) -> ObserverOut:
    """Put one already-detected anomaly into a sentence.

    Detection stays deterministic. This adds a reading to an anomaly that has
    already fired, and refuses to store one that cites a number the detector
    did not record.
    """
    exists = await session.scalar(select(Anomaly.id).where(Anomaly.id == anomaly_id))
    if exists is None:
        raise HTTPException(status_code=404, detail="anomaly not found")

    outcome = await read_anomaly(session, anomaly_id, settings=settings)
    return ObserverOut(**outcome.as_dict())


@router.post("/admin/x/collect", response_model=CollectionOut)
async def run_collector(
    session: SessionDep, settings: SettingsDep, admin: AdminDep
) -> CollectionOut:
    """Run each configured X search once and store what comes back.

    Returns 200 with `complete: false` when the quota stopped the run or no
    token is configured — a collector that returns zero posts for those reasons
    must not look like one that found nothing.
    """
    report = await collect_posts(session, settings=settings)
    return CollectionOut(**report.as_dict())


@router.post("/admin/chain/collect", response_model=ChainOut)
async def run_chain_collector(
    session: SessionDep, settings: SettingsDep, admin: AdminDep
) -> ChainOut:
    """Measure real tokens once and store one snapshot each.

    Holder counts stay null — a public node cannot supply them and this will not
    estimate one. The pipeline needs several measurements before any detector
    speaks, so the first runs are deliberately quiet.
    """
    report = await collect_chain(session, settings=settings)
    return ChainOut(**report.as_dict())


@router.post("/admin/go-live", response_model=GoLiveOut)
async def go_live(
    session: SessionDep,
    settings: SettingsDep,
    admin: AdminDep,
    confirm: bool = Query(
        default=False,
        description="Without this, nothing is deleted and only readiness is reported.",
    ),
) -> GoLiveOut:
    """Report whether there is enough real history to stop serving fixtures.

    With `confirm=true`, deletes the demo rows. Both halves of going live have
    to happen: the rows go, and `DEMO_MODE=false` is set in the environment.
    Deleting without the flag leaves an empty demo site; flipping the flag
    without deleting leaves hand-written experiments sitting next to real ones,
    and a visitor does not audit `is_demo` flags.

    It refuses to delete before the pipeline could observe anything. A live site
    with no research and no explanation reads as broken, which is worse than an
    honest demo.
    """
    from sqlalchemy import func, select

    from app.services.seed import clear_demo_rows

    tokens = (await session.scalars(select(Token).where(Token.is_demo.is_(False)))).all()
    depth: dict[str, int] = {}
    for token in tokens:
        depth[token.symbol or token.address[:8]] = int(
            await session.scalar(
                select(func.count())
                .select_from(TokenSnapshot)
                .where(TokenSnapshot.token_id == token.id)
            )
            or 0
        )

    needed = settings.observation_min_snapshots
    ready_tokens = sorted(name for name, count in depth.items() if count >= needed)

    demo_rows = int(
        await session.scalar(
            select(func.count()).select_from(Token).where(Token.is_demo.is_(True))
        )
        or 0
    )

    if not ready_tokens:
        return GoLiveOut(
            ready=False,
            deleted=False,
            demo_mode=settings.demo_mode,
            live_tokens=len(tokens),
            measurements_needed=needed,
            ready_tokens=[],
            deepest=max(depth.values(), default=0),
            demo_tokens=demo_rows,
            note=(
                f"No token has {needed} measurements yet, so the pipeline would "
                "observe nothing. Let the hourly collector run longer."
            ),
        )

    if not confirm:
        return GoLiveOut(
            ready=True,
            deleted=False,
            demo_mode=settings.demo_mode,
            live_tokens=len(tokens),
            measurements_needed=needed,
            ready_tokens=ready_tokens,
            deepest=max(depth.values(), default=0),
            demo_tokens=demo_rows,
            note=(
                "Ready. Call again with confirm=true to delete the demo rows, then "
                "set DEMO_MODE=false in the environment."
            ),
        )

    await clear_demo_rows(session)
    await session.commit()
    return GoLiveOut(
        ready=True,
        deleted=True,
        demo_mode=settings.demo_mode,
        live_tokens=len(tokens),
        measurements_needed=needed,
        ready_tokens=ready_tokens,
        deepest=max(depth.values(), default=0),
        demo_tokens=0,
        note=(
            "Demo rows deleted. Until DEMO_MODE=false is set in the environment, "
            "the pipeline still reads the fixture series."
        ),
    )
