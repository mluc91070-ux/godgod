"""Schemas for the X content pipeline and the token page."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DraftOut(ORMModel):
    id: str
    content_type: str
    body: str
    status: str
    reviewer_verdict: str | None
    reviewer_notes: str | None
    rejection_reason: str | None
    source_kind: str | None
    source_id: str | None
    approved_at: datetime | None
    approved_by: str | None
    created_at: datetime
    is_demo: bool


class DraftDecision(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


class AttentionOut(ORMModel):
    """One reading of a search ranking.

    `rank` is the measurement and lower means more looked-up. There is no row
    for a coin that was not in the list, so an absent token is unranked rather
    than ranked last. `token_id` is set only on an exact contract-address
    match — a matching symbol is not a link.
    """

    id: str
    observed_at: datetime
    source: str
    ref: str
    symbol: str | None
    name: str | None
    rank: int
    market_cap_rank: int | None
    chain: str | None
    address: str | None
    token_id: str | None
    is_demo: bool


class TokenOut(ORMModel):
    id: str
    address: str
    chain: str
    name: str | None
    symbol: str | None
    decimals: int | None
    launch_time: datetime | None
    launchpad: str | None
    migrated_to_dex: str | None
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    holders: int | None
    holder_concentration_top10: float | None
    source: str | None
    is_demo: bool
