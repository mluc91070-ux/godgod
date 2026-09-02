"""What people are looking up, as a measurement rather than a mood.

The social collector is gone. What it was for is not: a token's price and depth
say what happened in the pool, and nothing in the pool says whether anyone was
paying attention. That was the whole point of the social series, and losing it
left three detectors with no source.

This is the replacement, and it is a better measurement than the one it
replaces. A search-ranking feed reports *positions*, not sentiment: a token is
in the trending list or it is not, at a rank, at a time. Sampled every run that
is an ordinary time series — countable, comparable, and with no model anywhere
near it. A post had to be read to mean anything; a rank does not.

Two things make it usable at all, and neither is optional:

- **A token is linked on an exact contract address.** The feed's own coin
  detail carries `platforms`, chain to address, so the join is on the same
  identifier the collector already uses. Matching on a symbol would be the
  mistake the X rules already name: a `$SYMBOL` is not evidence about the row
  with that symbol, and two chains have a dozen of each.
- **Absent is absent.** A token missing from the list is *not ranked*, which
  is not the same as ranked last. No row is written for it, and no detector
  will ever see a zero this module invented.

The endpoint is configuration (`ATTENTION_API_URL`) for the same reason every
other one is. Read-only, no key, no account.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.untrusted import sanitize_external_text
from app.providers.base import ProviderNotConfigured


class AttentionCallFailed(RuntimeError):
    """The source answered with an error, or did not answer."""


@dataclass(frozen=True)
class TrendingCoin:
    """One entry in a ranking. Nothing here is a claim about a token yet."""

    ref: str
    """The source's own identifier. Kept so a resolution can be cached and so
    the row can be traced back to what was read."""
    symbol: str | None
    name: str | None
    rank: int
    """Position in the list, zero-based as the source reports it. Lower is more
    looked-up. This is the measurement."""
    market_cap_rank: int | None
    """The source's overall rank, if it has one. Context, not the signal."""


class AttentionProvider(ABC):
    name: str = "attention"
    implemented: bool = False

    @abstractmethod
    async def trending(self) -> list[TrendingCoin]: ...

    @abstractmethod
    async def platforms(self, ref: str) -> dict[str, str]: ...
    """Chain to contract address, as the source reports them. Empty when it
    knows the coin but not where it lives — which is common and is a reason to
    store nothing, never a reason to guess."""


class NullAttentionProvider(AttentionProvider):
    """What runs with no url. Refuses rather than reporting an empty list."""

    name = "attention-none"
    implemented = False

    async def trending(self) -> list[TrendingCoin]:
        raise ProviderNotConfigured(
            "ATTENTION_API_URL is not set. Nothing is measured about what people "
            "are looking up, and no row says a token was ignored."
        )

    async def platforms(self, ref: str) -> dict[str, str]:
        raise ProviderNotConfigured("ATTENTION_API_URL is not set")


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class HttpAttentionProvider(AttentionProvider):
    """Reads a ranking feed and the coin details behind it."""

    name = "attention"
    implemented = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.attention_api_url:
            raise ProviderNotConfigured("ATTENTION_API_URL is not set")
        self._settings = settings
        self._root = settings.attention_api_url.rstrip("/")
        self._client = client

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(
                f"{self._root}{path}",
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "godgod-research/0.1 (read-only)",
                },
            )

        try:
            if self._client is not None:
                response = await call(self._client)
            else:
                async with httpx.AsyncClient(
                    timeout=self._settings.attention_timeout_seconds,
                    follow_redirects=True,
                ) as client:
                    response = await call(client)
        except httpx.HTTPError as exc:
            raise AttentionCallFailed(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 429:
            # The keyless tier is rate-limited. Named, because the fix is
            # fewer calls per run rather than a different url.
            raise AttentionCallFailed("the attention source rate-limited the request")
        if response.status_code != 200:
            raise AttentionCallFailed(
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AttentionCallFailed(f"the source did not return JSON: {exc}") from exc

    async def trending(self) -> list[TrendingCoin]:
        payload = await self._get("/search/trending")
        entries = payload.get("coins") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise AttentionCallFailed(
                f"expected a list of coins, got {type(entries).__name__}"
            )

        found: list[TrendingCoin] = []
        for position, entry in enumerate(entries):
            item = (entry or {}).get("item") if isinstance(entry, dict) else None
            if not isinstance(item, dict) or not item.get("id"):
                continue
            # The source ships its own `score`, but position in the list is the
            # thing that cannot drift in meaning between releases.
            found.append(
                TrendingCoin(
                    ref=sanitize_external_text(str(item["id"]), max_len=128),
                    symbol=sanitize_external_text(str(item.get("symbol") or ""), max_len=32)
                    or None,
                    name=sanitize_external_text(str(item.get("name") or ""), max_len=128)
                    or None,
                    rank=position,
                    market_cap_rank=_int(item.get("market_cap_rank")),
                )
            )
        return found

    async def platforms(self, ref: str) -> dict[str, str]:
        payload = await self._get(
            f"/coins/{ref}",
            {
                "localization": "false",
                "tickers": "false",
                "market_data": "false",
                "community_data": "false",
                "developer_data": "false",
            },
        )
        raw = payload.get("platforms") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            return {}
        return {
            sanitize_external_text(str(chain), max_len=32).lower(): (
                sanitize_external_text(str(address), max_len=64).lower()
            )
            for chain, address in raw.items()
            if chain and address
        }


_cache: dict[tuple, AttentionProvider] = {}


def get_attention_provider(settings: Settings | None = None) -> AttentionProvider:
    settings = settings or get_settings()
    key = (settings.attention_api_url, settings.attention_timeout_seconds)
    if key not in _cache:
        _cache[key] = (
            HttpAttentionProvider(settings)
            if settings.attention_api_url
            else NullAttentionProvider()
        )
    return _cache[key]


def reset_attention_provider() -> None:
    _cache.clear()
