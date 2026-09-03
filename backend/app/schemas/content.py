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


class PairingOut(BaseModel):
    """One token, and what its deepest pool is currently priced in.

    Not an ORM row: the quote lives on the measurement and the identity lives
    on the token, so this is the join of the two — the newest measurement of
    each token that recorded a quote at all.
    """

    address: str
    chain: str
    symbol: str | None
    name: str | None
    observed_at: datetime
    quote_symbol: str | None
    quote_kind: str
    """`tokenised-equity`, `gas`, `other`, or `unknown` — the last of which
    means the source described the pair and it was neither of the first two.
    A token whose rows predate the column is absent entirely, because "not
    recorded" is not a kind and would otherwise be counted as one."""
    market_cap_usd: float | None
    liquidity_usd: float | None
    volume_usd: float | None
    source: str | None
    """The sampling frame that found it. `equity-quote` is the structural
    frame; the others reached it for unrelated reasons."""


class PairingSummary(BaseModel):
    """The split, and the cohort the pairing hypothesis is asked about."""

    counts: dict[str, int]
    """Live tokens by what they are priced in, from their newest measurement."""
    chains: dict[str, dict[str, int]]
    """The same split per chain. Held apart because every comparison here is,
    and because a chain with no equity wrappers reports an empty exposed arm
    that is a true statement about that chain rather than a gap."""
    equity_quoted: list[PairingOut]
    """Every live token currently priced in a tokenised equity, deepest first."""
    marker: str
    """The string the classification looks for in a quote token's name. Shown
    because the whole split depends on it: if the chain renames its wrappers
    this stops matching, and a reader should be able to see what was asked."""
    hypothesis_key: str
    """The template that compares the two arms. Nothing on this page is a
    result — the comparison is run by the research cycle and published with
    its own verdict, including INCONCLUSIVE."""
