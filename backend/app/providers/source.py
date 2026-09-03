"""Observation source.

`SolanaProvider` and `XProvider` (see base.py) are RPC/API shaped. The
observation pipeline does not consume RPC calls — it consumes *normalized
measurements over time*. This is that interface, and it sits one level above
the raw providers:

    SolanaProvider + market reads ─┐
                                   ├─▶ ObservationSource ─▶ pipeline
    XProvider search ─────────────┘

Two implementations exist: one reads the synthetic fixture series, the other
reads the rows the live collectors wrote. The pipeline consumes them
identically, which is the point — nothing in it changed when real data arrived.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.base import as_utc
from app.services.fixtures import load_fixture, parse_dt


@dataclass(frozen=True)
class TokenRef:
    address: str
    symbol: str | None
    name: str | None
    decimals: int | None
    launch_time: datetime | None
    launchpad: str | None


class ObservationSource(ABC):
    """What the observer needs, independent of where it comes from."""

    name: str
    is_demo: bool

    @abstractmethod
    async def list_tokens(self) -> list[TokenRef]: ...

    @abstractmethod
    async def get_snapshots(
        self, address: str, *, since: datetime | None = None, until: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Measurements ordered oldest first. Missing fields stay absent."""

    @abstractmethod
    async def get_posts(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        token_address: str | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def latest_timestamp(self) -> datetime | None:
        """Newest measurement available. The pipeline anchors its window here
        instead of on the wall clock, so a frozen dataset stays observable."""


class FixtureObservationSource(ObservationSource):
    """Reads `data/fixtures/timeseries.json`. Synthetic, and flagged as such."""

    name = "fixture-timeseries"
    is_demo = True

    def __init__(self, fixture: str = "timeseries.json") -> None:
        self._fixture = fixture
        self._data: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._data is None:
            self._data = load_fixture(self._fixture)
        return self._data

    async def list_tokens(self) -> list[TokenRef]:
        return [
            TokenRef(
                address=item["address"],
                symbol=item.get("symbol"),
                name=item.get("name"),
                decimals=item.get("decimals"),
                launch_time=parse_dt(item.get("launch_time")),
                launchpad=item.get("launchpad"),
            )
            for item in self._load()["tokens"]
        ]

    async def get_snapshots(
        self, address: str, *, since: datetime | None = None, until: datetime | None = None
    ) -> list[dict[str, Any]]:
        for token in self._load()["tokens"]:
            if token["address"] != address:
                continue
            rows = []
            for snapshot in token.get("snapshots", []):
                observed_at = parse_dt(snapshot["observed_at"])
                if since and observed_at < since:
                    continue
                if until and observed_at > until:
                    continue
                rows.append({**snapshot, "observed_at": observed_at})
            return sorted(rows, key=lambda row: row["observed_at"])
        return []

    async def get_posts(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        token_address: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = []
        for post in self._load().get("posts", []):
            posted_at = parse_dt(post.get("posted_at"))
            if posted_at is None:
                continue
            if since and posted_at < since:
                continue
            if until and posted_at > until:
                continue
            if token_address and post.get("mentions_token_address") != token_address:
                continue
            rows.append({**post, "posted_at": posted_at})
        return sorted(rows, key=lambda row: row["posted_at"])

    async def get_accounts(self) -> list[dict[str, Any]]:
        return list(self._load().get("accounts", []))

    async def latest_timestamp(self) -> datetime | None:
        moments: list[datetime] = []
        for token in self._load()["tokens"]:
            for snapshot in token.get("snapshots", []):
                parsed = parse_dt(snapshot["observed_at"])
                if parsed:
                    moments.append(parsed)
        return max(moments) if moments else None


class DatabaseObservationSource(ObservationSource):
    """Reads the measurements the live collectors stored.

    The chain collector writes `token_snapshots`; the X collector writes
    `social_posts`. This reads them back in the shape the pipeline expects, so
    a live run and a fixture replay are the same code path.

    It reports `is_demo=False` because the rows it serves are real. If the
    collectors have not run, it returns nothing — which the pipeline reports as
    "looked at nothing" rather than "found nothing".
    """

    name = "database-live"
    is_demo = False

    def __init__(self, session: Any) -> None:
        self._session = session

    async def list_tokens(self) -> list[TokenRef]:
        from sqlalchemy import select

        from app.models import Token

        rows = (
            await self._session.scalars(select(Token).where(Token.is_demo.is_(False)))
        ).all()
        return [
            TokenRef(
                address=row.address,
                symbol=row.symbol,
                name=row.name,
                decimals=row.decimals,
                launch_time=row.launch_time,
                launchpad=row.launchpad,
            )
            for row in rows
        ]

    async def get_snapshots(
        self, address: str, *, since: datetime | None = None, until: datetime | None = None
    ) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from app.models import Token, TokenSnapshot

        token = await self._session.scalar(select(Token).where(Token.address == address))
        if token is None:
            return []

        stmt = (
            select(TokenSnapshot)
            .where(TokenSnapshot.token_id == token.id)
            .order_by(TokenSnapshot.observed_at)
        )
        rows = (await self._session.scalars(stmt)).all()

        result = []
        for row in rows:
            observed_at = as_utc(row.observed_at)
            if since and observed_at < since:
                continue
            if until and observed_at > until:
                continue
            result.append(
                {
                    "observed_at": observed_at,
                    "market_cap_usd": row.market_cap_usd,
                    "liquidity_usd": row.liquidity_usd,
                    "volume_usd": row.volume_usd,
                    "holders": row.holders,
                    "holder_concentration_top10": row.holder_concentration_top10,
                    "transactions": row.transactions,
                    "buys": row.buys,
                    "sells": row.sells,
                    "age_seconds": row.age_seconds,
                    # A string, unlike everything above it. Detectors that read
                    # it must treat NULL as "not recorded" rather than as a
                    # kind: the column is newer than most of the series.
                    "quote_kind": row.quote_kind,
                    "quote_symbol": row.quote_symbol,
                }
            )
        return result

    async def get_posts(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        token_address: str | None = None,
    ) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from app.models import SocialPost

        stmt = select(SocialPost).where(SocialPost.is_demo.is_(False))
        if token_address:
            stmt = stmt.where(SocialPost.mentions_token_address == token_address)
        rows = (await self._session.scalars(stmt.order_by(SocialPost.posted_at))).all()

        result = []
        for row in rows:
            posted_at = as_utc(row.posted_at)
            if posted_at is None:
                continue
            if since and posted_at < since:
                continue
            if until and posted_at > until:
                continue
            result.append(
                {
                    "external_id": row.external_id,
                    "posted_at": posted_at,
                    "text": row.text,
                    "handle": row.account.handle if row.account else None,
                    "likes": row.likes,
                    "reposts": row.reposts,
                    "replies": row.replies,
                    "mentions_token_address": row.mentions_token_address,
                }
            )
        return result

    async def get_accounts(self) -> list[dict[str, Any]]:
        return []

    async def latest_timestamp(self) -> datetime | None:
        from sqlalchemy import func, select

        from app.models import TokenSnapshot

        newest = await self._session.scalar(select(func.max(TokenSnapshot.observed_at)))
        return as_utc(newest)


def get_observation_source(session: Any = None, settings: Any = None) -> ObservationSource:
    """Fixtures in demo mode, the live rows otherwise.

    With `DEMO_MODE=false` and no session to read from, this still returns the
    fixture source — but the caller is expected to pass one. The alternative
    (silently serving fixtures to a production pipeline) is the exact mixing of
    demo and real data the whole `is_demo` flag exists to prevent.
    """
    from app.core.config import get_settings

    settings = settings or get_settings()
    if not settings.demo_mode and session is not None:
        return DatabaseObservationSource(session)
    return FixtureObservationSource()
