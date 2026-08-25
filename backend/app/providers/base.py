"""Provider abstractions.

No vendor name appears in the interface. Concrete implementations arrive in
PHASE 7 (X) and PHASE 8 (Solana); until then only the demo/null providers
exist, and they say so.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class ProviderNotConfigured(RuntimeError):
    """Raised when a live provider is requested without credentials."""


class NotImplementedYet(NotImplementedError):
    """Explicit marker for planned-but-unbuilt capability."""


class SolanaProvider(ABC):
    """Read-only Solana access.

    V1 is READ ONLY by construction: there is no method here that can buy,
    sell, swap, transfer, mint, burn or touch liquidity, and no signing key
    ever enters the process.
    """

    name: str = "solana"

    @abstractmethod
    async def get_account(self, address: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def get_transaction(self, signature: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def get_token_accounts(self, mint: str, limit: int = 100) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_signatures(self, address: str, limit: int = 100) -> list[dict[str, Any]]: ...

    @abstractmethod
    def subscribe_logs(self, mentions: str | None = None) -> AsyncIterator[dict[str, Any]]: ...

    @abstractmethod
    def subscribe_account(self, address: str) -> AsyncIterator[dict[str, Any]]: ...

    @abstractmethod
    def subscribe_program(self, program_id: str) -> AsyncIterator[dict[str, Any]]: ...


class XProvider(ABC):
    """Social access. ``create_post`` is gated by X_MODE and autonomy level."""

    name: str = "x"

    @abstractmethod
    async def search_recent_posts(
        self, query: str, limit: int = 50, since_id: str | None = None
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_user(self, handle: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def get_user_posts(self, handle: str, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_mentions(self, limit: int = 50) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def create_post(self, text: str, reply_to: str | None = None) -> dict[str, Any]: ...
