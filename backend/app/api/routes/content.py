"""Drafts, token information, and the attention readings.

Nothing here can publish. ``/publish`` exists so the contract is visible,
and it refuses: V1 never posts automatically.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import AdminDep, PageDep, SessionDep, SettingsDep, build_page, count_query
from app.core.enums import AnomalyType, DraftStatus
from app.models import AttentionSnapshot, ContentDraft, Token, TokenSnapshot
from app.models.base import utcnow
from app.providers.market import EQUITY_QUOTE
from app.schemas.common import Page
from app.schemas.content import (
    AttentionOut,
    DraftDecision,
    DraftOut,
    PairingOut,
    PairingSummary,
    TokenOut,
)
from app.services.research.templates import TEMPLATES_BY_ANOMALY

router = APIRouter(prefix="/api", tags=["content"])


async def _get_draft(session: SessionDep, draft_id: str) -> ContentDraft:
    draft = await session.scalar(select(ContentDraft).where(ContentDraft.id == draft_id))
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    return draft


@router.get("/x/drafts", response_model=Page[DraftOut])
async def list_drafts(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> Page:
    stmt = select(ContentDraft).order_by(ContentDraft.created_at.desc())
    if status_filter:
        stmt = stmt.where(ContentDraft.status == status_filter.upper())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, DraftOut, total, page, settings)


@router.post("/x/drafts/{draft_id}/approve", response_model=DraftOut)
async def approve_draft(
    session: SessionDep, admin: AdminDep, draft_id: str, decision: DraftDecision
) -> ContentDraft:
    draft = await _get_draft(session, draft_id)
    if draft.status == DraftStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="draft is already published")
    if not draft.source_kind:
        raise HTTPException(
            status_code=422,
            detail="draft has no recorded source; an unsourced claim cannot be approved",
        )
    draft.status = str(DraftStatus.APPROVED)
    draft.approved_at = utcnow()
    draft.approved_by = decision.actor
    draft.reviewer_notes = decision.notes
    draft.rejection_reason = None
    await session.commit()
    await session.refresh(draft)
    return draft


@router.post("/x/drafts/{draft_id}/reject", response_model=DraftOut)
async def reject_draft(
    session: SessionDep, admin: AdminDep, draft_id: str, decision: DraftDecision
) -> ContentDraft:
    draft = await _get_draft(session, draft_id)
    if draft.status == DraftStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="draft is already published")
    draft.status = str(DraftStatus.REJECTED)
    draft.rejection_reason = decision.notes or "rejected by operator"
    draft.approved_at = None
    draft.approved_by = None
    await session.commit()
    await session.refresh(draft)
    return draft


@router.post("/x/drafts/{draft_id}/publish")
async def publish_draft(
    session: SessionDep, settings: SettingsDep, admin: AdminDep, draft_id: str
) -> dict:
    """Publish one approved draft, if the deployment is configured to publish.

    Answers 501 while `X_MODE` is anything other than "publish" — not because
    the code is missing, but because a deployment that has not opted in has not
    opted in. The response says which of the two it is.
    """
    from app.services.publish import publish_next

    await _get_draft(session, draft_id)

    if settings.x_mode != "publish":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": "this deployment does not publish",
                "x_mode": settings.x_mode,
                "autonomy_level": settings.autonomy_level,
                "note": (
                    "The publishing path is implemented. Set X_MODE=publish and the "
                    "four OAuth values to enable it; the drafts stay here until then."
                ),
            },
        )

    outcome = await publish_next(session, settings=settings, draft_id=draft_id)
    if not outcome.published:
        raise HTTPException(status_code=409, detail=outcome.as_dict())
    return outcome.as_dict()


@router.get("/tokens", response_model=Page[TokenOut])
async def list_tokens(session: SessionDep, settings: SettingsDep, page: PageDep) -> Page:
    stmt = select(Token).order_by(Token.created_at.desc())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, TokenOut, total, page, settings)


@router.get("/attention", response_model=Page[AttentionOut])
async def list_attention(
    session: SessionDep, settings: SettingsDep, page: PageDep
) -> Page:
    """The most recent readings of the search ranking, newest first.

    Nothing here is derived. Every row is a position the feed reported at a
    time, and a coin the feed did not list has no row at all.
    """
    stmt = select(AttentionSnapshot).order_by(
        AttentionSnapshot.observed_at.desc(), AttentionSnapshot.rank
    )
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, AttentionOut, total, page, settings)


@router.get("/pairings", response_model=PairingSummary)
async def list_pairings(session: SessionDep, settings: SettingsDep) -> PairingSummary:
    """What the measured tokens are priced in, and the equity-quoted cohort.

    A price is a ratio, and this is the denominator. A meme quoted in a
    tokenised share of a company is not the same instrument as a meme quoted
    in the chain's gas token: its chart is not separable from that company's
    without the pair data, and the depth on the equity side is a constraint on
    the meme side.

    Nothing here is a result. It is the population of one hypothesis, shown
    before that hypothesis has an answer, so the two arms can be seen to exist
    rather than asserted to. The comparison itself is run by the research cycle
    and published with its own verdict.

    Read from the newest measurement of each token, never from the token row:
    the quote belongs to the pool the price came from, and a token that gains a
    deeper pool against a different asset has genuinely changed denomination.
    A token whose rows all predate the column reports nothing and is absent —
    "not recorded" is not a kind.
    """
    newest = (
        select(
            TokenSnapshot.token_id.label("token_id"),
            func.max(TokenSnapshot.observed_at).label("observed_at"),
        )
        .where(TokenSnapshot.is_demo.is_(False), TokenSnapshot.quote_kind.is_not(None))
        .group_by(TokenSnapshot.token_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Token, TokenSnapshot)
            .join(TokenSnapshot, TokenSnapshot.token_id == Token.id)
            .join(
                newest,
                (TokenSnapshot.token_id == newest.c.token_id)
                & (TokenSnapshot.observed_at == newest.c.observed_at),
            )
            .where(Token.is_demo.is_(False))
        )
    ).all()

    counts: dict[str, int] = {}
    chains: dict[str, dict[str, int]] = {}
    equity: list[PairingOut] = []
    for token, snapshot in rows:
        kind = str(snapshot.quote_kind)
        counts[kind] = counts.get(kind, 0) + 1
        per_chain = chains.setdefault(token.chain or "unrecorded", {})
        per_chain[kind] = per_chain.get(kind, 0) + 1
        if kind != EQUITY_QUOTE:
            continue
        equity.append(
            PairingOut(
                address=token.address,
                chain=token.chain,
                symbol=token.symbol,
                name=token.name,
                observed_at=snapshot.observed_at,
                quote_symbol=snapshot.quote_symbol,
                quote_kind=kind,
                market_cap_usd=snapshot.market_cap_usd,
                liquidity_usd=snapshot.liquidity_usd,
                volume_usd=snapshot.volume_usd,
                source=token.source,
            )
        )
    equity.sort(key=lambda item: item.liquidity_usd or 0.0, reverse=True)

    return PairingSummary(
        counts=counts,
        chains=chains,
        equity_quoted=equity,
        marker=settings.equity_quote_marker,
        hypothesis_key=TEMPLATES_BY_ANOMALY[str(AnomalyType.QUOTE_ASSET_PAIRING)].key,
    )


@router.get("/tokens/{address}", response_model=TokenOut)
async def get_token(session: SessionDep, address: str) -> Token:
    row = await session.scalar(select(Token).where(Token.address == address))
    if row is None:
        raise HTTPException(status_code=404, detail="token not found")
    return row
