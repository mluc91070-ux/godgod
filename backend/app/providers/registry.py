"""Provider availability reporting.

PHASE 1 ships the interfaces only. This module tells the truth about what is
configured and what is actually built, so the UI never implies a live feed
that does not exist.
"""

from __future__ import annotations

from app.agents.base import IMPLEMENTED_AGENTS
from app.core.config import Settings, get_settings
from app.schemas.common import ProviderStatus


def _solana_note(settings: Settings) -> str:
    """Read-only, and specific about what a node cannot answer."""
    if not settings.solana_rpc_url:
        return (
            "Read-only JSON-RPC client implemented; SOLANA_RPC_URL is not set, so "
            "no chain data is read. No signing path exists in any configuration."
        )
    return (
        "Reading accounts, supply and the largest token accounts. Holder *counts* "
        "need an indexer and are recorded as null, never estimated. Read-only: "
        "there is no signing path."
    )


def _market_note(settings: Settings) -> str:
    if not settings.market_api_url:
        return (
            "Liquidity, volume and trade counts are not measured: MARKET_API_URL "
            "is unset, so the chain collector records nothing rather than zeroes."
        )
    chains = ", ".join(settings.market_chains) or "none"
    retained = (
        f" Tokens above ${settings.chain_retain_min_market_cap_usd:,.0f} market cap are "
        f"re-measured every run, at most {settings.chain_retain_max_tokens} per chain, "
        "and keep being measured after they fall through the floors — the drain is the "
        "outcome, not a reason to stop looking."
        if settings.chain_retain_max_tokens > 0
        else " Retention is off: a token is measured only while the feed still names it."
    )
    return (
        f"Measuring tokens above ${settings.chain_min_liquidity_usd:,.0f} liquidity, "
        f"at most {settings.chain_max_tokens} per run, on {chains}. The promotion "
        "feed decides the split between chains; it is not rebalanced here. Holder "
        "distributions are read on Solana only — the RPC client speaks one chain, "
        "and elsewhere the share is recorded null rather than estimated." + retained
    )


def _launchpad_note(settings: Settings) -> str:
    """The migration frame as one source serves it.

    This is the API-backed launchpad, which covers one chain. The other chain's
    launch contracts are read directly over a node and are reported under
    `evm`, so a reader can tell which half is missing when one is.
    """
    if not settings.launchpad_migrations:
        return "Migrations are switched off. No token is marked as migrated."
    if not settings.launchpad_api_url:
        return (
            "Bonding curve states are not read: LAUNCHPAD_API_URL is unset, so "
            "every token keeps bonding_curve_state NULL rather than being "
            "assumed unmigrated."
        )
    return (
        f"Reading completed curves, at most {settings.launchpad_max_tokens} per "
        f"run, measured above ${settings.launchpad_min_liquidity_usd:,.0f} "
        "liquidity — a lower floor than the promotion feed, because a token "
        "minutes past migration is thin by construction, not parked. This "
        "endpoint covers one chain; the other is read from its launch "
        "contracts over a node, reported separately."
    )


def _evm_note(settings: Settings) -> str:
    """The second chain's node, and the one fact it is there for."""
    if not settings.evm_rpc_url:
        return (
            "Read-only JSON-RPC client implemented; EVM_RPC_URL is not set, so no "
            "bonding curve state is read on that chain and no token there is marked "
            "as migrated. Read-only in every configuration: four methods, none of "
            "which can sign or send."
        )
    if not settings.evm_launchpad_factories:
        return (
            "Node configured, but EVM_LAUNCHPAD_FACTORIES is empty, so no launch "
            "event is read. The addresses are deliberately not compiled in: three "
            "published as the factory for this launchpad were checked against the "
            "chain and none of them emitted the event."
        )
    return (
        f"Reading {settings.evm_launchpad_status_call} on "
        f"{len(settings.evm_launchpad_factories)} launch contract(s) over the last "
        f"{settings.evm_launchpad_lookback_blocks:,} blocks, at most "
        f"{settings.evm_launchpad_max_calls} status calls per run. Only a curve the "
        "contract reports complete is recorded as migrated; a call that reverts is "
        "counted as unreadable, never as unmigrated. Read-only: no signing path."
    )


def _x_note(settings: Settings) -> str:
    """Read access only, and only when a token is present."""
    if not settings.x_bearer_token:
        return (
            "Beta testing, and not connected: the recent-search client is implemented "
            "but no bearer token is set, so nothing is collected and the collector says "
            "so rather than reporting zero posts. Beta describes the code, not a "
            "capability — nothing is being read and nothing is being published."
        )
    return (
        f"Beta testing: reading recent posts for {len(settings.x_search_terms)} queries, "
        f"at most {settings.x_max_posts_per_run} posts per run. Publishing refuses — "
        f"X_MODE={settings.x_mode}, and the four OAuth values a write needs are not set. "
        "Read access working is not the same capability as publishing, so the two are "
        "reported apart."
    )


def _model_note(settings: Settings) -> str:
    """What the model layer can actually do right now, in one sentence."""
    if not settings.anthropic_api_key:
        return (
            "Client implemented; no API key set, so every model-backed agent refuses "
            "rather than runs. The deterministic engines are unaffected."
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
    # Named from the roster rather than listed by hand: this sentence said
    # "writer and reviewer" for two releases after the critic and the observer
    # gained a model, which is a status line describing an older deployment.
    return (
        f"{len(IMPLEMENTED_AGENTS)} model-backed agents enabled "
        f"({', '.join(IMPLEMENTED_AGENTS)}); daily budget "
        f"${settings.llm_daily_budget_usd:.2f}."
    )


def describe_providers(settings: Settings | None = None) -> list[ProviderStatus]:
    settings = settings or get_settings()
    return [
        ProviderStatus(
            name="solana",
            configured=bool(settings.solana_rpc_url),
            implemented=True,
            note=_solana_note(settings),
        ),
        ProviderStatus(
            name="market",
            configured=bool(settings.market_api_url),
            implemented=True,
            note=_market_note(settings),
        ),
        ProviderStatus(
            name="launchpad",
            configured=bool(settings.launchpad_api_url),
            implemented=True,
            note=_launchpad_note(settings),
        ),
        ProviderStatus(
            name="evm",
            configured=bool(
                settings.evm_rpc_url and settings.evm_launchpad_factories
            ),
            implemented=True,
            note=_evm_note(settings),
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
