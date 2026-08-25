"""Observation source.

`SolanaProvider` and `XProvider` (see base.py) are RPC/API shaped. The
observation pipeline does not consume RPC calls — it consumes *normalized
measurements over time*. This is that interface, and it sits one level above
the raw providers:

    SolanaProvider + market reads ─┐
                                   ├─▶ ObservationSource ─▶ pipeline
    XProvider search ─────────────┘

Today the only implementation reads the synthetic fixture time series. When
the live providers land, a second implementation fills the same interface and
the pipeline does not change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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


def get_observation_source() -> ObservationSource:
    """Only one implementation exists today, and it is fixture-backed.

    When a live source is added this returns it based on configuration; until
    then it must not pretend there is a choice.
    """
    return FixtureObservationSource()
