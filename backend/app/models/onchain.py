"""On-chain entities: tokens, wallets, wallet clusters.

Only fields that a provider can actually deliver are modelled. A missing
measurement stays NULL — it is never back-filled with a guess.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONDict
from app.models.base import Entity


class Token(Entity):
    __tablename__ = "tokens"
    __table_args__ = (UniqueConstraint("address", "chain", name="uq_tokens_address_chain"),)
    """Unique on the pair, because an address alone does not name a token.

    It was unique on the address while one chain was read. A second chain makes
    that constraint wrong in both directions: it would reject a legitimate
    token whose address string collides with one on another network, and — the
    worse half — the lookup that goes with it would fold two different assets
    into one row and interleave their measurements into a single series.
    """

    address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(32), default="solana", nullable=False)
    """Which network the token lives on. Never inferred from the address
    format: it is recorded from what the market source reported."""
    name: Mapped[str | None] = mapped_column(String(256))
    symbol: Mapped[str | None] = mapped_column(String(64))
    decimals: Mapped[int | None] = mapped_column(Integer)

    launch_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bonding_curve_state: Mapped[str | None] = mapped_column(String(64))
    migrated_to_dex: Mapped[str | None] = mapped_column(String(64))
    launchpad: Mapped[str | None] = mapped_column(String(64))

    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Latest known snapshot values. NULL means "not measured", not zero.
    market_cap_usd: Mapped[float | None] = mapped_column(Float)
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    volume_24h_usd: Mapped[float | None] = mapped_column(Float)
    holders: Mapped[int | None] = mapped_column(Integer)
    holder_concentration_top10: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str | None] = mapped_column(String(128))
    raw_metadata: Mapped[dict | None] = mapped_column(JSONDict)
    """Untrusted third-party metadata (name/symbol/uri). Never an instruction."""

    snapshots: Mapped[list[TokenSnapshot]] = relationship(
        back_populates="token", cascade="all, delete-orphan"
    )


class TokenSnapshot(Entity):
    """Point-in-time measurement of a token. The basis of every experiment."""

    __tablename__ = "token_snapshots"

    token_id: Mapped[str] = mapped_column(ForeignKey("tokens.id", ondelete="CASCADE"), index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    market_cap_usd: Mapped[float | None] = mapped_column(Float)
    fdv_usd: Mapped[float | None] = mapped_column(Float)
    """Fully diluted valuation, stored apart from market cap rather than in
    place of it. See `MarketSnapshot`."""
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    volume_usd: Mapped[float | None] = mapped_column(Float)
    holders: Mapped[int | None] = mapped_column(Integer)
    holder_concentration_top10: Mapped[float | None] = mapped_column(Float)
    transactions: Mapped[int | None] = mapped_column(Integer)
    buys: Mapped[int | None] = mapped_column(Integer)
    sells: Mapped[int | None] = mapped_column(Integer)
    age_seconds: Mapped[int | None] = mapped_column(Integer)
    liquidity_change_pct: Mapped[float | None] = mapped_column(Float)
    holder_change_pct: Mapped[float | None] = mapped_column(Float)

    source: Mapped[str | None] = mapped_column(String(128))
    selected_by: Mapped[str | None] = mapped_column(String(32))
    """Why this measurement was taken: `discovery`, `migration` or `retention`.

    Not the same question as `Token.source`, which records the frame that first
    found the token and is written once. This records the rule that put *this
    row* in the dataset, and the rules are not interchangeable — a retained row
    skips the liquidity and volume floors on purpose, because a token that had
    a large market cap and then drained is the single most informative row
    there is and dropping it would be survivorship bias by construction.

    NULL on every row written before the distinction existed. That is "not
    recorded", not "discovery"."""

    token: Mapped[Token] = relationship(back_populates="snapshots")


class LaunchpadLaunch(Entity):
    """A token seen launching on a bonding curve, and whether it ever finished.

    This table exists because the two halves of one fact live in different
    places and arrive at different times. The launch is a log entry, readable
    only two thousand blocks at a time; the graduation is contract state that
    changes hours or days later. No single query holds both, so the launch is
    written down and re-asked.

    `graduated` is deliberately three-valued:

    - `True` — the contract said the curve completed.
    - `False` — the contract said it had not, at `checked_at`.
    - `NULL` — nobody has managed to ask, or the contract refused. Not
      "did not migrate". A launch that was never resolved keeps NULL for good,
      and that is the honest record of a question nobody answered.
    """

    __tablename__ = "launchpad_launches"
    __table_args__ = (
        UniqueConstraint("chain", "address", name="uq_launches_chain_address"),
    )

    chain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    factory: Mapped[str] = mapped_column(String(64), nullable=False)
    """The contract that emitted the launch. Kept because the status call goes
    back to the same one — the topic is not unique to a single launchpad."""
    launched_at_block: Mapped[int] = mapped_column(Integer, nullable=False)
    graduated: Mapped[bool | None] = mapped_column(Boolean)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When the status was last read. NULL means never successfully read."""
    graduated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When this system first saw it complete — not when the curve filled. The
    chain knows the second; this row only ever knew the first."""


class ChainCursor(Entity):
    """How far a chain has been scanned, per named scan.

    Without it a windowed scan either re-reads the same blocks forever or skips
    whatever happened while the process was down, and the second failure is
    invisible: missing launches look exactly like a launchpad nobody uses.
    """

    __tablename__ = "chain_cursors"
    __table_args__ = (UniqueConstraint("chain", "name", name="uq_cursors_chain_name"),)

    chain: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    block: Mapped[int] = mapped_column(Integer, nullable=False)
    """The last block scanned, inclusive."""


class Wallet(Entity):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("address", name="uq_wallets_address"),)

    address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(32), default="solana", nullable=False)
    label: Mapped[str | None] = mapped_column(String(256))
    """Third-party label. Untrusted text, never an instruction."""
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cluster_id: Mapped[str | None] = mapped_column(
        ForeignKey("wallet_clusters.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    cluster: Mapped[WalletCluster | None] = relationship(back_populates="wallets")


class WalletCluster(Entity):
    """A set of wallets grouped by an explicitly recorded heuristic."""

    __tablename__ = "wallet_clusters"

    label: Mapped[str | None] = mapped_column(String(256))
    method: Mapped[str] = mapped_column(String(128), nullable=False)
    """How the cluster was derived. Required for reproducibility."""
    confidence: Mapped[float | None] = mapped_column(Float)
    size: Mapped[int | None] = mapped_column(Integer)
    evidence: Mapped[dict | None] = mapped_column(JSONDict)

    wallets: Mapped[list[Wallet]] = relationship(back_populates="cluster")
