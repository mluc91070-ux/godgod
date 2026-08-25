"""Provider availability reporting.

PHASE 1 ships the interfaces only. This module tells the truth about what is
configured and what is actually built, so the UI never implies a live feed
that does not exist.
"""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.schemas.common import ProviderStatus


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
            implemented=False,
            note="Interface only. Search/draft client lands in PHASE 7.",
        ),
        ProviderStatus(
            name="anthropic",
            configured=bool(settings.anthropic_api_key),
            implemented=False,
            note="No model is called in PHASE 1.",
        ),
    ]
