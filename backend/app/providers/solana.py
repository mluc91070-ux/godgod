"""Solana read access (PHASE 8).

JSON-RPC over whatever `SOLANA_RPC_URL` points at. No vendor name appears here
— the endpoint is configuration, so moving between providers is an environment
change and not a code change.

**Read only, by construction.** The methods here fetch account data, holder
distribution and signatures. There is no method that constructs, signs or
submits anything, no key material enters this process, and the security test
fails the build if a signing symbol ever appears in the codebase.

What this module deliberately does *not* do is invent a measurement. A public
RPC node cannot tell you how many holders a token has — that needs an indexer.
So `holders` stays `None`, the detectors that need it return no verdict, and
nothing downstream pretends otherwise.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.providers.base import NotImplementedYet, ProviderNotConfigured, SolanaProvider

LAMPORTS_PER_SOL = 1_000_000_000


class RpcCallFailed(RuntimeError):
    """The node answered with an error, or did not answer."""


@dataclass(frozen=True)
class HolderDistribution:
    """What `getTokenLargestAccounts` can actually tell us.

    The node returns the largest *token accounts*, capped at 20. Two honest
    limits ride along and are recorded rather than smoothed over:

    - These are accounts, not people. A liquidity pool, a burn address and a
      team multisig each look like one large holder.
    - 20 accounts is not the whole distribution, so this is a top-N share and
      never a Gini coefficient or a holder count.
    """

    top10_share: float | None
    accounts_seen: int
    supply: float | None

    @property
    def measurable(self) -> bool:
        return self.top10_share is not None


class NullSolanaProvider(SolanaProvider):
    """What runs with no RPC url. Refuses; never returns an empty result."""

    name = "solana-none"
    implemented = False

    async def get_account(self, address: str):
        raise ProviderNotConfigured(
            "SOLANA_RPC_URL is not set. No chain data is read until it is, and "
            "the collector reports that rather than reporting zero tokens."
        )

    async def get_transaction(self, signature: str):
        raise ProviderNotConfigured("SOLANA_RPC_URL is not set")

    async def get_token_accounts(self, mint: str, limit: int = 100):
        raise ProviderNotConfigured("SOLANA_RPC_URL is not set")

    async def get_signatures(self, address: str, limit: int = 100):
        raise ProviderNotConfigured("SOLANA_RPC_URL is not set")

    def subscribe_logs(self, mentions: str | None = None) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedYet("websocket subscriptions are not implemented")

    def subscribe_account(self, address: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedYet("websocket subscriptions are not implemented")

    def subscribe_program(self, program_id: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedYet("websocket subscriptions are not implemented")


class HttpSolanaProvider(SolanaProvider):
    """JSON-RPC client. Every method is a read."""

    name = "solana"
    implemented = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.solana_rpc_url:
            raise ProviderNotConfigured("SOLANA_RPC_URL is not set")
        self._settings = settings
        self._url = settings.solana_rpc_url
        self._client = client

    async def _rpc(self, method: str, params: list[Any]) -> Any:
        """One JSON-RPC call, with a single retry on a rate limit.

        Shared public endpoints throttle the heavier methods —
        `getTokenLargestAccounts` in particular — so one backoff is worth
        trying. Two would be pretending the endpoint is something it is not:
        past that, the honest outcome is an unmeasured field.
        """
        body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(self._url, json=body)

        async def once() -> httpx.Response:
            if self._client is not None:
                return await call(self._client)
            async with httpx.AsyncClient(
                timeout=self._settings.solana_timeout_seconds
            ) as client:
                return await call(client)

        try:
            response = await once()
            if response.status_code == 429 and self._settings.solana_retry_seconds > 0:
                await asyncio.sleep(self._settings.solana_retry_seconds)
                response = await once()
        except httpx.HTTPError as exc:
            raise RpcCallFailed(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 429:
            raise RpcCallFailed(
                f"the RPC endpoint rate-limited {method}, twice. Shared public "
                "endpoints throttle the heavier reads; point SOLANA_RPC_URL at a "
                "dedicated one to measure holder concentration."
            )
        if response.status_code != 200:
            raise RpcCallFailed(f"HTTP {response.status_code}: {response.text[:300]}")

        payload = response.json()
        if "error" in payload:
            raise RpcCallFailed(f"rpc error: {str(payload['error'])[:300]}")
        return payload.get("result")

    async def get_account(self, address: str) -> dict[str, Any] | None:
        result = await self._rpc(
            "getAccountInfo", [address, {"encoding": "jsonParsed", "commitment": "confirmed"}]
        )
        return (result or {}).get("value")

    async def get_transaction(self, signature: str) -> dict[str, Any] | None:
        return await self._rpc(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
        )

    async def get_token_accounts(self, mint: str, limit: int = 100) -> list[dict[str, Any]]:
        """Largest token accounts. The node caps this at 20, whatever we ask."""
        result = await self._rpc("getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
        return ((result or {}).get("value") or [])[:limit]

    async def get_signatures(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        return (
            await self._rpc(
                "getSignaturesForAddress", [address, {"limit": max(1, min(limit, 1000))}]
            )
            or []
        )

    async def get_supply(self, mint: str) -> float | None:
        result = await self._rpc("getTokenSupply", [mint, {"commitment": "confirmed"}])
        value = (result or {}).get("value") or {}
        amount = value.get("uiAmount")
        return float(amount) if amount is not None else None

    async def get_holder_distribution(self, mint: str) -> HolderDistribution:
        """Top-10 share of supply, or an explicitly unmeasurable result."""
        accounts = await self.get_token_accounts(mint, limit=20)
        supply = await self.get_supply(mint)

        amounts = [
            float(item.get("uiAmount"))
            for item in accounts
            if item.get("uiAmount") is not None
        ]
        if not amounts or not supply:
            # Missing, not zero. A token whose supply the node would not report
            # has an unknown distribution, not a flat one.
            return HolderDistribution(
                top10_share=None, accounts_seen=len(accounts), supply=supply
            )

        top10 = sum(sorted(amounts, reverse=True)[:10])
        return HolderDistribution(
            top10_share=min(1.0, top10 / supply),
            accounts_seen=len(accounts),
            supply=supply,
        )

    def subscribe_logs(self, mentions: str | None = None) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedYet(
            "websocket subscriptions are not implemented; the collector polls."
        )

    def subscribe_account(self, address: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedYet("websocket subscriptions are not implemented")

    def subscribe_program(self, program_id: str) -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedYet("websocket subscriptions are not implemented")


_cache: dict[tuple, SolanaProvider] = {}


def get_solana_provider(settings: Settings | None = None) -> SolanaProvider:
    settings = settings or get_settings()
    key = (settings.solana_rpc_url, settings.solana_timeout_seconds)
    provider = _cache.get(key)
    if provider is None:
        provider = (
            HttpSolanaProvider(settings) if settings.solana_rpc_url else NullSolanaProvider()
        )
        _cache[key] = provider
    return provider


def reset_solana_provider() -> None:
    _cache.clear()
