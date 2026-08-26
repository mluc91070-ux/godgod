"""Provider availability reporting.

PHASE 1 ships the interfaces only. This module tells the truth about what is
configured and what is actually built, so the UI never implies a live feed
that does not exist.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.schemas.common import ProviderStatus


def _x_note(settings: Settings) -> str:
    """Read access only, and only when a token is present."""
    if not settings.x_bearer_token:
        return (
            "Recent-search client implemented; no bearer token set, so nothing is "
            "collected and the collector says so rather than reporting zero posts."
        )
    return (
        f"Reading recent posts for {len(settings.x_search_terms)} queries, at most "
        f"{settings.x_max_posts_per_run} posts per run. Publishing refuses: "
        f"X_MODE={settings.x_mode}."
    )


def _model_note(settings: Settings) -> str:
    """What the model layer can actually do right now, in one sentence."""
    if not settings.anthropic_api_key:
        return (
            "Client implemented; no API key set, so the writer and reviewer agents "
            "refuse rather than run. The deterministic engines are unaffected."
        )
    missing = [
        role
        for role in ("model_writer", "model_critic")
        if not getattr(settings, role, None)
    ]
    if missing:
        return f"Key set, but {', '.join(role.upper() for role in missing)} is unset."
    if (
        settings.model_price_input_usd_per_mtok is None
        or settings.model_price_output_usd_per_mtok is None
    ):
        return (
            "Key and roles set, but MODEL_PRICE_* is unset: the budget guard refuses "
            "to spend what it cannot measure."
        )
    return f"Writer and reviewer agents enabled; daily budget ${settings.llm_daily_budget_usd:.2f}."


def describe_providers(settings: Settings | None = None) -> list[ProviderStatus]:
    settings = settings or get_settings()
    return [
        ProviderStatus(
            name="solana",
            configured=bool(settings.solana_rpc_url),
            implemented=False,
            note="Interface only. Read-only client lands in PHASE 8.",
        ),
        ProviderStatus(
            name="x",
            configured=bool(settings.x_bearer_token),
            implemented=True,
            note=_x_note(settings),
        ),
        ProviderStatus(
            name="anthropic",
            configured=bool(settings.anthropic_api_key),
            implemented=True,
            note=_model_note(settings),
        ),
    ]
