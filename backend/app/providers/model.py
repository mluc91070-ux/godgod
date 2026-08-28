"""The model provider.

One interface, two implementations: a null provider that refuses clearly, and an
HTTP client for the configured messages API. No model name appears here — roles
(`MODEL_FAST`, `MODEL_REASONING`, `MODEL_WRITER`, `MODEL_CRITIC`) resolve through
settings, so changing a model is configuration and never a code change.

Cost is reported, not guessed. If per-token prices are not configured the
response carries `cost_usd=None` and the caller records "unknown" — a fabricated
zero would defeat the budget it is supposed to protect.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.untrusted import SYSTEM_RULE
from app.providers.base import ProviderNotConfigured

MODEL_ROLES = ("MODEL_FAST", "MODEL_REASONING", "MODEL_WRITER", "MODEL_CRITIC")

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class ModelCallFailed(RuntimeError):
    """The provider answered with an error, or did not answer.

    Raised rather than swallowed: an agent that silently returns nothing when
    the model failed is indistinguishable from an agent that found nothing.
    """


@dataclass(frozen=True)
class ModelResponse:
    text: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    stop_reason: str | None
    cost_usd: float | None
    """None means "not priced", never "free"."""

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"


def model_for_role(settings: Settings, role: str) -> str:
    """Resolve a role to the configured model id."""
    if role not in MODEL_ROLES:
        raise ValueError(f"unknown model role {role!r}; expected one of {MODEL_ROLES}")
    configured = getattr(settings, role.lower(), None)
    if not configured:
        raise ProviderNotConfigured(
            f"{role} is not set. Model roles are configuration: set {role} in the "
            "environment rather than hard-coding a model name."
        )
    return str(configured)


def price(settings: Settings, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """Estimated cost, or None when prices are unconfigured."""
    rate_in = settings.model_price_input_usd_per_mtok
    rate_out = settings.model_price_output_usd_per_mtok
    if rate_in is None or rate_out is None:
        return None
    return round(
        (input_tokens or 0) / 1_000_000 * rate_in + (output_tokens or 0) / 1_000_000 * rate_out,
        6,
    )


class ModelProvider(ABC):
    name: str = "model"
    implemented: bool = False

    @abstractmethod
    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        role: str,
        max_tokens: int = 1024,
        effort: str | None = "low",
    ) -> ModelResponse: ...


class NullModelProvider(ModelProvider):
    """What runs when no key is configured. It refuses; it never pretends."""

    name = "none"
    implemented = False

    async def complete(self, **_: Any) -> ModelResponse:
        raise ProviderNotConfigured(
            "No model provider is configured. Set ANTHROPIC_API_KEY and the MODEL_* "
            "roles to enable model-backed agents. Until then the deterministic "
            "engines run and the drafts they produce say they are templated."
        )


class HttpModelProvider(ModelProvider):
    """Messages-API client over httpx.

    The system rule about untrusted content is prepended to every system prompt
    here rather than in each agent, so no agent can forget it.

    Effort defaults to "low": every call this system makes writes or judges one
    short post, and the deep reasoning a higher setting pays for is spent on a
    task that does not need it.
    """

    name = "anthropic"
    implemented = True

    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise ProviderNotConfigured("ANTHROPIC_API_KEY is not set")
        self._settings = settings
        self._key = settings.anthropic_api_key
        self._workspace = settings.anthropic_workspace_id
        self._timeout = settings.model_timeout_seconds

    async def complete(
        self,
        *,
        system: str,
        prompt: str,
        role: str,
        max_tokens: int = 1024,
        effort: str | None = "low",
    ) -> ModelResponse:
        model = model_for_role(self._settings, role)
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": f"{SYSTEM_RULE}\n\n{system}",
            "messages": [{"role": "user", "content": prompt}],
        }

        # No `temperature`: current models reject it with a 400, not a warning —
        # found by the first real call. Sampling is no longer a knob. `effort`
        # is what decides how much thinking a request pays for, and every call
        # this system makes writes or judges one short post.
        if effort:
            payload["output_config"] = {"effort": effort}

        headers = {
            "x-api-key": self._key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        # An identity-linked key authenticates the person rather than the
        # workspace a request acts in, and the API answers 400 until the
        # workspace is named. Sent only when configured: a workspace-scoped key
        # neither needs it nor wants it.
        if self._workspace:
            headers["anthropic-workspace-id"] = self._workspace

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(API_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise ModelCallFailed(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code != 200:
            # The body can contain the request back; keep the excerpt short so a
            # failure never dumps a prompt into the event log.
            raise ModelCallFailed(f"HTTP {response.status_code}: {response.text[:300]}")

        body = response.json()
        blocks = body.get("content", [])
        text = "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        ).strip()
        usage = body.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")

        if not text:
            raise ModelCallFailed("the provider returned no text")

        return ModelResponse(
            text=text,
            model=body.get("model", model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=body.get("stop_reason"),
            cost_usd=price(self._settings, input_tokens, output_tokens),
        )


_cache: dict[tuple, ModelProvider] = {}


def get_model_provider(settings: Settings | None = None) -> ModelProvider:
    settings = settings or get_settings()
    key = (settings.anthropic_api_key, settings.model_timeout_seconds)
    provider = _cache.get(key)
    if provider is None:
        provider = (
            HttpModelProvider(settings) if settings.anthropic_api_key else NullModelProvider()
        )
        _cache[key] = provider
    return provider


def reset_model_provider() -> None:
    """Drop the cache. Used by tests and after a settings change."""
    _cache.clear()
