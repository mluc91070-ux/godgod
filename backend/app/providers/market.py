"""Market measurements for a token: liquidity, volume, price, trade counts.

An RPC node knows what is on chain. It does not know what a token is worth or
how much of it traded, because that lives in the pools of decentralised
exchanges and in the aggregators that index them. This is the interface for
that, and — like the RPC — the endpoint is configuration (`MARKET_API_URL`), so
no vendor name is compiled into the system.

The response is normalised into the same field names `token_snapshots` uses.
Anything the source does not report stays `None`: a token with no reported
volume did not trade zero, it was not measured.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.untrusted import sanitize_external_text
from app.providers.base import ProviderNotConfigured


class MarketCallFailed(RuntimeError):
    """The market source answered with an error, or did not answer."""


@dataclass(frozen=True)
class MarketSnapshot:
    """One measurement. Every field is optional because every field can be absent."""

    address: str
    symbol: str | None = None
    name: str | None = None
    price_usd: float | None = None
    market_cap_usd: float | None = None
    liquidity_usd: float | None = None
    volume_usd: float | None = None
    """Traded in the last hour, matching the snapshot cadence."""
    volume_24h_usd: float | None = None
    """Kept for the liquidity floor, which is a question about the token
    overall rather than about this hour."""
    transactions: int | None = None
    buys: int | None = None
    sells: int | None = None
    created_at: datetime | None = None
    pairs_seen: int = 0

    @property
    def age_seconds(self) -> int | None:
        if self.created_at is None:
            return None
        return int((datetime.now(UTC) - self.created_at).total_seconds())

    def as_snapshot_fields(self) -> dict[str, Any]:
        """The subset `token_snapshots` stores. Absent stays absent."""
        return {
            "market_cap_usd": self.market_cap_usd,
            "liquidity_usd": self.liquidity_usd,
            "volume_usd": self.volume_usd,
            "transactions": self.transactions,
            "buys": self.buys,
            "sells": self.sells,
            "age_seconds": self.age_seconds,
        }


class MarketProvider(ABC):
    name: str = "market"
    implemented: bool = False

    @abstractmethod
    async def get_snapshot(self, address: str) -> MarketSnapshot | None: ...

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> list[MarketSnapshot]: ...

    @abstractmethod
    async def discover(self, limit: int = 30) -> list[MarketSnapshot]: ...


class NullMarketProvider(MarketProvider):
    """What runs with no market url. Refuses rather than reporting zeroes."""

    name = "market-none"
    implemented = False

    async def get_snapshot(self, address: str) -> MarketSnapshot | None:
        raise ProviderNotConfigured(
            "MARKET_API_URL is not set. Liquidity, volume and trade counts are "
            "not measured, so no token snapshot can be recorded."
        )

    async def search(self, query: str, limit: int = 20) -> list[MarketSnapshot]:
        raise ProviderNotConfigured("MARKET_API_URL is not set")

    async def discover(self, limit: int = 30) -> list[MarketSnapshot]:
        raise ProviderNotConfigured("MARKET_API_URL is not set")


def _number(value: Any) -> float | None:
    """Parse a number, or return None. Never a default."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _from_pair(address: str, pairs: list[dict[str, Any]]) -> MarketSnapshot | None:
    """Fold the pairs for one token into a single measurement.

    A token trades in several pools. Liquidity and volume are summed because
    they are additive; price is taken from the deepest pool rather than
    averaged, because an average across pools of different depth is a number
    that describes no trade anyone could make.
    """
    relevant = [
        pair
        for pair in pairs
        if (pair.get("baseToken") or {}).get("address", "").lower() == address.lower()
    ]
    if not relevant:
        return None

    deepest = max(
        relevant, key=lambda pair: _number((pair.get("liquidity") or {}).get("usd")) or 0.0
    )
    base = deepest.get("baseToken") or {}

    def total(extract) -> float | None:
        values = [extract(pair) for pair in relevant]
        present = [value for value in values if value is not None]
        return sum(present) if present else None

    def total_int(extract) -> int | None:
        value = total(extract)
        return int(value) if value is not None else None

    created_ms = _number(deepest.get("pairCreatedAt"))

    # The one-hour window, not the twenty-four hour one, because snapshots are
    # taken hourly. Two consecutive readings of a 24h rolling figure overlap by
    # 96%, so a volume spike is smeared across a day and the detector that
    # looks for one would never see it. The measurement has to match the
    # cadence it is sampled at.
    txns_1h = lambda pair: (pair.get("txns") or {}).get("h1") or {}  # noqa: E731

    return MarketSnapshot(
        address=address,
        # Names and symbols are attacker-controlled strings on a permissionless
        # chain; they are sanitised before they are ever stored or displayed.
        symbol=sanitize_external_text(str(base.get("symbol") or ""), max_len=32) or None,
        name=sanitize_external_text(str(base.get("name") or ""), max_len=128) or None,
        price_usd=_number(deepest.get("priceUsd")),
        market_cap_usd=_number(deepest.get("marketCap") or deepest.get("fdv")),
        liquidity_usd=total(lambda pair: _number((pair.get("liquidity") or {}).get("usd"))),
        volume_usd=total(lambda pair: _number((pair.get("volume") or {}).get("h1"))),
        volume_24h_usd=total(lambda pair: _number((pair.get("volume") or {}).get("h24"))),
        buys=total_int(lambda pair: _int(txns_1h(pair).get("buys"))),
        sells=total_int(lambda pair: _int(txns_1h(pair).get("sells"))),
        transactions=total_int(
            lambda pair: (
                None
                if _int(txns_1h(pair).get("buys")) is None
                and _int(txns_1h(pair).get("sells")) is None
                else (_int(txns_1h(pair).get("buys")) or 0)
                + (_int(txns_1h(pair).get("sells")) or 0)
            )
        ),
        created_at=(
            datetime.fromtimestamp(created_ms / 1000, tz=UTC) if created_ms else None
        ),
        pairs_seen=len(relevant),
    )


class HttpMarketProvider(MarketProvider):
    """Reads token pairs from the configured market API."""

    name = "market"
    implemented = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.market_api_url:
            raise ProviderNotConfigured("MARKET_API_URL is not set")
        self._settings = settings
        self._root = settings.market_api_url.rstrip("/")
        self._client = client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(
                f"{self._root}{path}",
                params=params,
                headers={"User-Agent": "godgod-research/0.1 (read-only)"},
            )

        try:
            if self._client is not None:
                response = await call(self._client)
            else:
                async with httpx.AsyncClient(
                    timeout=self._settings.market_timeout_seconds, follow_redirects=True
                ) as client:
                    response = await call(client)
        except httpx.HTTPError as exc:
            raise MarketCallFailed(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 429:
            raise MarketCallFailed("the market API rate-limited the request")
        if response.status_code != 200:
            raise MarketCallFailed(f"HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    async def get_snapshot(self, address: str) -> MarketSnapshot | None:
        payload = await self._get(f"/tokens/v1/solana/{address}")
        pairs = payload if isinstance(payload, list) else (payload.get("pairs") or [])
        return _from_pair(address, pairs)

    async def search(self, query: str, limit: int = 20) -> list[MarketSnapshot]:
        payload = await self._get("/latest/dex/search", {"q": query})
        pairs = payload.get("pairs") or []
        solana = [pair for pair in pairs if pair.get("chainId") == "solana"]

        seen: dict[str, list[dict[str, Any]]] = {}
        for pair in solana:
            address = (pair.get("baseToken") or {}).get("address")
            if address:
                seen.setdefault(address, []).append(pair)

        snapshots = [
            snapshot
            for address, group in seen.items()
            if (snapshot := _from_pair(address, group)) is not None
        ]
        snapshots.sort(key=lambda item: item.liquidity_usd or 0.0, reverse=True)
        return snapshots[:limit]

    async def discover(self, limit: int = 30) -> list[MarketSnapshot]:
        """Tokens currently being promoted, measured.

        Search matches names, which on a permissionless chain mostly returns
        clones of whatever was typed — a query for "solana" finds pools holding
        a billion dollars of wrapped SOL that traded a hundred dollars all day.
        The population this system studies is the one people are actively
        pushing, so discovery reads the promotion feed and measures those.

        Being promoted is not evidence of anything. It is a sampling frame, and
        every experiment records it as one.
        """
        payload = await self._get("/token-boosts/latest/v1")
        entries = payload if isinstance(payload, list) else (payload.get("data") or [])
        addresses = [
            entry["tokenAddress"]
            for entry in entries
            if entry.get("chainId") == "solana" and entry.get("tokenAddress")
        ]
        # Keep first-seen order while removing repeats: the same token is
        # promoted several times and must not be measured twice.
        unique: list[str] = []
        for address in addresses:
            if address not in unique:
                unique.append(address)

        snapshots: list[MarketSnapshot] = []
        for batch_start in range(0, min(len(unique), limit), 25):
            batch = unique[batch_start : batch_start + 25]
            payload = await self._get(f"/tokens/v1/solana/{','.join(batch)}")
            pairs = payload if isinstance(payload, list) else (payload.get("pairs") or [])
            grouped: dict[str, list[dict[str, Any]]] = {}
            for pair in pairs:
                address = (pair.get("baseToken") or {}).get("address")
                if address:
                    grouped.setdefault(address, []).append(pair)
            snapshots.extend(
                snapshot
                for address, group in grouped.items()
                if (snapshot := _from_pair(address, group)) is not None
            )

        snapshots.sort(key=lambda item: item.volume_usd or 0.0, reverse=True)
        return snapshots[:limit]


_cache: dict[tuple, MarketProvider] = {}


def get_market_provider(settings: Settings | None = None) -> MarketProvider:
    settings = settings or get_settings()
    key = (settings.market_api_url, settings.market_timeout_seconds)
    provider = _cache.get(key)
    if provider is None:
        provider = (
            HttpMarketProvider(settings) if settings.market_api_url else NullMarketProvider()
        )
        _cache[key] = provider
    return provider


def reset_market_provider() -> None:
    _cache.clear()
