"""Running the model-backed agents, and reporting what they cost.

Every endpoint here spends money, so every one requires the operator token and
every one reports what it spent. A run that made no call because the budget
refused it is a 200 with `ok: false` and the reason — not a silent no-op.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.agents import review_draft, write_draft_for_result
from app.api.deps import AdminDep, SessionDep, SettingsDep
from app.models import ContentDraft, ExperimentResult
from app.schemas.agents import BudgetOut, ChainOut, CollectionOut, ReviewOut, WriterOut
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
