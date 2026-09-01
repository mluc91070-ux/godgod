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
from app.core.keccak import event_topic, function_selector
from app.core.untrusted import sanitize_external_text
from app.providers.base import ProviderNotConfigured
from app.providers.evm import (
    EvmCallFailed,
    EvmProvider,
    EvmReverted,
    address_from_topic,
    encode_address_arg,
    get_evm_provider,
    words,
)


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


@dataclass(frozen=True)
class LaunchEvent:
    """One launch, as the chain reported it."""

    address: str
    factory: str
    block: int


class EvmLaunchpadProvider(LaunchpadProvider):
    """Bonding curves read off an EVM chain, with no API in between.

    There is no endpoint to call for this launchpad — the ones that exist want
    a key — so the contract is read instead. Two primitives, both ordinary node
    calls, and neither of them keeps state:

    - `scan_launches` reads the launch event over a block range. Its first
      indexed parameter is the token.
    - `graduation_status` calls the status view on the factory that emitted it.

    Deciding *which* blocks to scan and remembering what was found belongs to
    a service with a database, not here: this node caps `eth_getLogs` at two
    thousand blocks per request — measured, it says so in the error — and a
    curve finishes hours or days after the launch that started it. A window
    wide enough to hold both does not exist. See `services/launchpad_scan.py`.

    Three ways this refuses to guess:

    - **A revert is not a "no".** The same event signature is emitted on this
      chain by a contract with no such view, and asking it reverts. That is
      returned as `None` — unreadable — never as "not graduated".
    - **A factory is never assumed.** The addresses are configuration and
      default to empty. Three published as the factory for this launchpad were
      checked against the chain and none of them emitted the event; the ones
      that do were found by asking the chain itself, with a topic filter and no
      address at all.
    - **A range too wide is split, not truncated.** Silently reading the last
      two thousand blocks of a ten-thousand block request would report a quiet
      launchpad.
    """

    name = "launchpad-evm"
    implemented = True

    def __init__(self, settings: Settings, evm: EvmProvider | None = None) -> None:
        if not settings.evm_rpc_url:
            raise ProviderNotConfigured("EVM_RPC_URL is not set")
        if not settings.evm_launchpad_factories:
            raise ProviderNotConfigured("EVM_LAUNCHPAD_FACTORIES is empty")
        self._settings = settings
        self._evm = evm or get_evm_provider(settings)
        self.factories = [address.lower() for address in settings.evm_launchpad_factories]
        self._topic = event_topic(settings.evm_launchpad_event)
        self._selector = function_selector(settings.evm_launchpad_status_call)

    async def head_block(self) -> int:
        """The newest block, after checking the node is on the right chain.

        Without the check a mistyped url writes one chain's tokens into
        another's rows, and nothing downstream could ever tell.
        """
        expected = self._settings.evm_chain_id
        try:
            if expected is not None:
                actual = await self._evm.chain_id()
                if actual != expected:
                    raise LaunchpadCallFailed(
                        f"the node reports chain id {actual}, expected {expected}"
                    )
            return await self._evm.block_number()
        except EvmCallFailed as exc:
            raise LaunchpadCallFailed(f"{type(exc).__name__}: {exc}") from exc

    async def scan_launches(self, from_block: int, to_block: int) -> list[LaunchEvent]:
        """Launches in a block range, in chunks the node accepts.

        Filtered by topic rather than by address, and the address checked
        afterwards: a node that quietly ignored an address filter would
        otherwise hand back another contract's launches as this one's.
        """
        chunk = max(1, self._settings.evm_log_chunk_blocks)
        allowed = set(self.factories)
        found: list[LaunchEvent] = []
        start = from_block
        try:
            while start <= to_block:
                end = min(to_block, start + chunk - 1)
                logs = await self._evm.get_logs(
                    from_block=start, to_block=end, topics=[self._topic]
                )
                for entry in logs:
                    factory = str(entry.get("address", "")).lower()
                    topics = entry.get("topics") or []
                    if factory not in allowed or len(topics) < 2:
                        continue
                    found.append(
                        LaunchEvent(
                            address=address_from_topic(str(topics[1])),
                            factory=factory,
                            block=int(str(entry.get("blockNumber", "0x0")), 16),
                        )
                    )
                start = end + 1
        except EvmCallFailed as exc:
            raise LaunchpadCallFailed(f"{type(exc).__name__}: {exc}") from exc
        return found

    async def graduation_status(self, factory: str, token: str) -> bool | None:
        """True, False, or None for "the contract did not answer".

        The third distinction is the point. A revert here means this contract
        has no opinion about this token, which is not the same claim as a curve
        that has not finished.
        """
        try:
            answer = await self._evm.call(
                factory, self._selector + encode_address_arg(token)
            )
        except EvmReverted:
            return None
        except EvmCallFailed as exc:
            raise LaunchpadCallFailed(f"{type(exc).__name__}: {exc}") from exc

        fields = words(answer)
        if len(fields) < 3:
            return None
        return int(fields[2], 16) == 1

    async def recent_migrations(self, limit: int = 30) -> list[MigratedToken]:
        """Not served here.

        The interface exists for a source that can answer "what migrated
        recently" in one call. A chain cannot: the launches are in logs behind
        a two-thousand block cap and the graduations are in contract state read
        one token at a time, so answering it needs a cursor and a table.
        `services/launchpad_scan.py` owns both and calls the two primitives
        above. Raising is the honest response — returning an empty list would
        report a launchpad where nothing ever graduates.
        """
        raise LaunchpadCallFailed(
            "an EVM launchpad is scanned incrementally, not queried; see "
            "services/launchpad_scan.py"
        )


_cache: dict[tuple, LaunchpadProvider] = {}


def get_launchpad_provider(
    settings: Settings | None = None, chain: str = "solana"
) -> LaunchpadProvider:
    """The launchpad for one chain, or a provider that says there is none.

    Two sources, because the two chains have nothing in common here: one
    launchpad publishes an API, the other publishes a contract. Both produce
    `MigratedToken`, so the collector never learns the difference.
    """
    settings = settings or get_settings()
    if chain == settings.evm_chain:
        key = (
            "evm",
            settings.evm_rpc_url,
            tuple(settings.evm_launchpad_factories),
            settings.evm_launchpad_event,
        )
        if key not in _cache:
            try:
                _cache[key] = EvmLaunchpadProvider(settings)
            except ProviderNotConfigured:
                _cache[key] = NullLaunchpadProvider()
        return _cache[key]

    key = ("http", settings.launchpad_api_url, settings.launchpad_timeout_seconds)
    if key not in _cache:
        _cache[key] = (
            HttpLaunchpadProvider(settings)
            if settings.launchpad_api_url
            else NullLaunchpadProvider()
        )
    return _cache[key]


def reset_launchpad_provider() -> None:
    _cache.clear()
