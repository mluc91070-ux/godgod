"""Tokens that finished their bonding curve.

Most tokens on a launchpad never leave it. The ones that do have crossed a
threshold somebody paid for, which makes "migrated" a sampling frame with a
property the promotion feed does not have: **it is not a purchase**. A boost is
bought; a completed curve is bought by the crowd, one buy at a time.

This module reads migrations and nothing else. It does not read new mints, it
does not rank, and it does not measure — the market provider does the
measuring, exactly as it does for the promotion feed, so a migrated token and a
promoted token produce identical `token_snapshots` rows and stay comparable.

What it refuses to do:

- **Infer a migration.** `completed` is a field the launchpad reports. A token
  whose curve state is absent is skipped, never assumed finished because its
  market cap looks high enough.
- **Name a destination it was not told.** `migrated_to_dex` comes from the pool
  key present in the payload. No key, no claim.
- **Report an empty answer as a quiet market.** A failed or unconfigured call
  raises, and the collector records the reason.

The host is configuration (`LAUNCHPAD_API_URL`) for the same reason the RPC is:
no vendor name belongs in the code. The response shape below is the shape that
host serves.
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


class LaunchpadCallFailed(RuntimeError):
    """The launchpad answered with an error, or did not answer."""


@dataclass(frozen=True)
class MigratedToken:
    """One token that completed its curve. Every field but the address is optional."""

    address: str
    symbol: str | None = None
    name: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    """When the curve finished. Absent on a source that reports only the state."""
    pool: str | None = None
    """The pool it migrated into, as named by the launchpad. None means the
    payload did not say — never a guess from the token's own address."""
    market_cap_usd: float | None = None
    """The launchpad's own figure. Kept for provenance; the snapshot stored by
    the collector comes from the market provider, so the two never mix."""

    @property
    def age_seconds(self) -> int | None:
        if self.created_at is None:
            return None
        return int((datetime.now(UTC) - self.created_at).total_seconds())


class LaunchpadProvider(ABC):
    name: str = "launchpad"
    implemented: bool = False

    @abstractmethod
    async def recent_migrations(self, limit: int = 30) -> list[MigratedToken]: ...


class NullLaunchpadProvider(LaunchpadProvider):
    """No url, no migrations. It says so rather than returning an empty list."""

    name = "launchpad-null"
    implemented = False

    async def recent_migrations(self, limit: int = 30) -> list[MigratedToken]:
        raise ProviderNotConfigured(
            "LAUNCHPAD_API_URL is not set. Migration events are unavailable and "
            "no token is marked as migrated."
        )


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None  # NaN is not a measurement


def _timestamp(value: Any) -> datetime | None:
    """Milliseconds since the epoch, as this class of API reports them.

    Rejects anything outside a plausible range instead of producing a token
    that launched in 1970 or in the year 55000 — an age of forty years would
    silently pass every age filter downstream.
    """
    raw = _number(value)
    if raw is None:
        return None
    seconds = raw / 1000.0 if raw > 1e11 else raw
    if not 1_000_000_000 < seconds < 4_000_000_000:
        return None
    return datetime.fromtimestamp(seconds, tz=UTC)


def _pool(entry: dict[str, Any]) -> str | None:
    """The destination pool, under whichever key this payload uses.

    Ordered from most specific to least: a key naming the destination market is
    better evidence than a generic one. All of them are addresses the caller
    can check on chain.
    """
    for key in ("pump_swap_pool", "raydium_pool", "pool_address", "market_id"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _from_entry(entry: dict[str, Any]) -> MigratedToken | None:
    address = entry.get("mint") or entry.get("address") or entry.get("tokenAddress")
    if not isinstance(address, str) or not address.strip():
        return None

    # The curve state is read, never inferred. `completed` absent means the
    # source did not say, and a token nobody said had migrated has not.
    completed = entry.get("complete")
    if completed is None:
        completed = entry.get("completed")
    if completed is not True:
        return None

    return MigratedToken(
        address=address.strip(),
        # Names and symbols are user-supplied strings from a permissionless
        # launchpad. They are data, and they are fenced on the way in.
        symbol=sanitize_external_text(str(entry.get("symbol") or ""), max_len=32) or None,
        name=sanitize_external_text(str(entry.get("name") or ""), max_len=128) or None,
        created_at=_timestamp(entry.get("created_timestamp") or entry.get("created_at")),
        completed_at=_timestamp(
            entry.get("completed_timestamp") or entry.get("migrated_at")
        ),
        pool=_pool(entry),
        market_cap_usd=_number(entry.get("usd_market_cap") or entry.get("market_cap_usd")),
    )


class HttpLaunchpadProvider(LaunchpadProvider):
    """Reads completed curves from the configured launchpad API."""

    name = "launchpad"
    implemented = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.launchpad_api_url:
            raise ProviderNotConfigured("LAUNCHPAD_API_URL is not set")
        self._settings = settings
        self._root = settings.launchpad_api_url.rstrip("/")
        self._client = client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(
                f"{self._root}{path}",
                params=params,
                headers={
                    "User-Agent": "godgod-research/0.1 (read-only)",
                    "Accept": "application/json",
                },
            )

        try:
            if self._client is not None:
                response = await call(self._client)
            else:
                async with httpx.AsyncClient(
                    timeout=self._settings.launchpad_timeout_seconds, follow_redirects=True
                ) as client:
                    response = await call(client)
        except httpx.HTTPError as exc:
            raise LaunchpadCallFailed(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 429:
            raise LaunchpadCallFailed("the launchpad rate-limited the request")
        if response.status_code != 200:
            raise LaunchpadCallFailed(
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise LaunchpadCallFailed(f"the launchpad did not return JSON: {exc}") from exc

    async def recent_migrations(self, limit: int = 30) -> list[MigratedToken]:
        """The most recently created tokens whose curve has completed.

        Sorted by creation rather than by market cap on purpose: sorting by cap
        returns the same handful of survivors every run, which is a leaderboard,
        not a sample. Creation order gives the cohort that migrated recently,
        including the ones about to go nowhere — and those are half the evidence.

        The completed filter is also re-applied locally. A server-side filter
        that silently stops working would otherwise fill the table with tokens
        marked as migrated that never were.
        """
        payload = await self._get(
            "/coins",
            {
                "limit": max(1, min(limit, 100)),
                "offset": 0,
                "sort": "created_timestamp",
                "order": "DESC",
                "complete": "true",
            },
        )
        entries = payload if isinstance(payload, list) else (payload.get("data") or [])
        if not isinstance(entries, list):
            raise LaunchpadCallFailed(
                f"expected a list of tokens, got {type(entries).__name__}"
            )

        seen: set[str] = set()
        migrations: list[MigratedToken] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            token = _from_entry(entry)
            if token is None or token.address in seen:
                continue
            seen.add(token.address)
            migrations.append(token)
        return migrations[:limit]


_cache: dict[tuple, LaunchpadProvider] = {}


def get_launchpad_provider(settings: Settings | None = None) -> LaunchpadProvider:
    settings = settings or get_settings()
    key = (settings.launchpad_api_url, settings.launchpad_timeout_seconds)
    if key not in _cache:
        _cache[key] = (
            HttpLaunchpadProvider(settings)
            if settings.launchpad_api_url
            else NullLaunchpadProvider()
        )
    return _cache[key]


def reset_launchpad_provider() -> None:
    _cache.clear()
