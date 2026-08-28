"""On-chain entities: tokens, wallets, wallet clusters.

Only fields that a provider can actually deliver are modelled. A missing
measurement stays NULL — it is never back-filled with a guess.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONDict
from app.models.base import Entity


class Token(Entity):
    __tablename__ = "tokens"
    __table_args__ = (UniqueConstraint("address", name="uq_tokens_address"),)

    address: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(32), default="solana", nullable=False)
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

    token: Mapped[Token] = relationship(back_populates="snapshots")


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
