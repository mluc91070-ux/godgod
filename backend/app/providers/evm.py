"""Read-only JSON-RPC access to an EVM chain.

The Solana provider exists because a market API cannot say who holds what. This
exists for the same kind of reason: a market API cannot say whether a bonding
curve finished. That fact lives in a launchpad contract, and on an EVM chain a
contract is readable by anyone with a node — no key, no vendor, no account.

Like every provider here the endpoint is configuration (`EVM_RPC_URL`), so the
chain being read is a deployment decision rather than a line of code.

**Read only by construction.** There are four methods and not one of them can
write: `eth_chainId`, `eth_blockNumber`, `eth_getLogs`, `eth_call`. There is no
`eth_sendRawTransaction`, no signer, no key material, and no code path that
could construct a transaction. `eth_call` executes against a block without
committing anything — it is how a `view` function is read, and a node would
reject a state change from it.

Two things measured against the live endpoint rather than assumed:

- **It rate-limits.** A burst of calls returns HTTP 429. That is reported as
  its own failure, not folded into a generic error, because the fix is pacing
  rather than a different url.
- **A revert is not an answer.** Calling a function on a contract that does not
  implement it reverts, and a revert must never be read as "false". Measured:
  the same event signature is emitted by two different contracts on this chain,
  and only one of them answers the follow-up call.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.providers.base import ProviderNotConfigured


class EvmCallFailed(RuntimeError):
    """The node answered with an error, or did not answer."""


class EvmReverted(EvmCallFailed):
    """The contract rejected the call.

    Kept apart from every other failure because it means something different:
    the node is healthy and the contract has no answer for this question. A
    caller that treats it as a `false` is inventing a measurement.
    """


class EvmProvider(ABC):
    """Read-only EVM access. Nothing here can sign, send or change state."""

    name: str = "evm"
    implemented: bool = False

    @abstractmethod
    async def chain_id(self) -> int: ...

    @abstractmethod
    async def block_number(self) -> int: ...

    @abstractmethod
    async def get_logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topics: list[str | None] | None = None,
        address: str | None = None,
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def call(self, to: str, data: str) -> str: ...


class NullEvmProvider(EvmProvider):
    """What runs with no url. Refuses rather than returning nothing found."""

    name = "evm-none"
    implemented = False

    async def chain_id(self) -> int:
        raise ProviderNotConfigured("EVM_RPC_URL is not set")

    async def block_number(self) -> int:
        raise ProviderNotConfigured("EVM_RPC_URL is not set")

    async def get_logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topics: list[str | None] | None = None,
        address: str | None = None,
    ) -> list[dict[str, Any]]:
        raise ProviderNotConfigured(
            "EVM_RPC_URL is not set. Bonding curve states on this chain are not "
            "read, so no token is marked as migrated rather than being assumed "
            "unmigrated."
        )

    async def call(self, to: str, data: str) -> str:
        raise ProviderNotConfigured("EVM_RPC_URL is not set")


def address_from_topic(topic: str) -> str:
    """The low 20 bytes of a 32-byte topic, as a lowercase 0x address.

    An indexed `address` parameter is left-padded into a full word. Slicing the
    padding off is the whole decode, and doing it in one named place keeps the
    off-by-two nobody would ever spot out of three call sites.
    """
    return "0x" + topic[-40:].lower()


def words(data: str) -> list[str]:
    """Split ABI return data or log data into 32-byte hex words."""
    body = data[2:] if data.startswith("0x") else data
    return [body[index : index + 64] for index in range(0, len(body) - 63, 64)]


def encode_address_arg(address: str) -> str:
    """One `address` argument, left-padded to a word. No ABI library needed for
    a single static parameter, and pulling one in for this would be the same
    trade `core/keccak.py` declined."""
    return address[2:].lower().rjust(64, "0")


class HttpEvmProvider(EvmProvider):
    name = "evm"
    implemented = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.evm_rpc_url:
            raise ProviderNotConfigured("EVM_RPC_URL is not set")
        self._settings = settings
        self._url = settings.evm_rpc_url
        self._client = client

    async def _rpc(self, method: str, params: list[Any]) -> Any:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

        async def send(client: httpx.AsyncClient) -> httpx.Response:
            return await client.post(
                self._url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "godgod-research/0.1 (read-only)",
                },
            )

        attempts = 1 + max(0, self._settings.evm_retries)
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                if self._client is not None:
                    response = await send(self._client)
                else:
                    async with httpx.AsyncClient(
                        timeout=self._settings.evm_timeout_seconds
                    ) as client:
                        response = await send(client)
            except httpx.HTTPError as exc:
                raise EvmCallFailed(f"{type(exc).__name__}: {exc}") from exc

            if response.status_code == 429:
                # Measured on the public endpoint: a burst of calls is refused.
                # One backoff is worth trying; more would be pretending a shared
                # endpoint is a dedicated one — the same call the Solana
                # provider makes, for the same reason.
                last = EvmCallFailed(f"the node rate-limited {method}")
                if attempt + 1 < attempts:
                    await asyncio.sleep(self._settings.evm_retry_seconds * (attempt + 1))
                    continue
                raise last
            if response.status_code != 200:
                raise EvmCallFailed(f"HTTP {response.status_code}: {response.text[:200]}")

            try:
                body = response.json()
            except ValueError as exc:
                raise EvmCallFailed(f"the node did not return JSON: {exc}") from exc

            error = body.get("error")
            if error:
                message = str(error.get("message", error))
                if "revert" in message.lower():
                    raise EvmReverted(message)
                raise EvmCallFailed(f"{method}: {message}")
            return body.get("result")

        raise last or EvmCallFailed(f"{method}: no answer")

    async def chain_id(self) -> int:
        return int(await self._rpc("eth_chainId", []), 16)

    async def block_number(self) -> int:
        return int(await self._rpc("eth_blockNumber", []), 16)

    async def get_logs(
        self,
        *,
        from_block: int,
        to_block: int,
        topics: list[str | None] | None = None,
        address: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"fromBlock": hex(from_block), "toBlock": hex(to_block)}
        if topics:
            query["topics"] = topics
        if address:
            query["address"] = address
        result = await self._rpc("eth_getLogs", [query])
        return result if isinstance(result, list) else []

    async def call(self, to: str, data: str) -> str:
        """One `eth_call` against the latest block.

        An empty result is returned as-is rather than raising. "The contract
        returned nothing" and "the contract refused" are different states, and
        only the second is an `EvmReverted`.
        """
        result = await self._rpc("eth_call", [{"to": to, "data": data}, "latest"])
        return result if isinstance(result, str) else "0x"


_cache: dict[tuple, EvmProvider] = {}


def get_evm_provider(settings: Settings | None = None) -> EvmProvider:
    settings = settings or get_settings()
    key = (settings.evm_rpc_url, settings.evm_timeout_seconds, settings.evm_retries)
    if key not in _cache:
        _cache[key] = (
            HttpEvmProvider(settings) if settings.evm_rpc_url else NullEvmProvider()
        )
    return _cache[key]


def reset_evm_provider() -> None:
    _cache.clear()
