"""Pre-deploy check: is this configuration safe to put on the internet?

Run it against the environment you are about to deploy with:

    DATABASE_URL=... DEMO_MODE=false ADMIN_TOKEN=... python scripts/preflight.py

It refuses on anything that would make the deployed system unsafe or dishonest,
warns on anything that would make it merely disappointing, and prints exactly
what the system will claim about itself once it is up — because "what does
/api/status say" is the question this project answers to.

Exit code 0 means safe to deploy. Non-zero means fix it first.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

BLOCKERS: list[str] = []
WARNINGS: list[str] = []


def blocker(condition: bool, message: str) -> None:
    if condition:
        BLOCKERS.append(message)


def warn(condition: bool, message: str) -> None:
    if condition:
        WARNINGS.append(message)


async def main() -> int:
    from app.core.config import get_settings
    from app.main import create_app
    from app.providers.registry import describe_providers

    settings = get_settings()
    production = settings.environment == "production"

    print(f"environment      {settings.environment}")
    print(f"demo mode        {settings.demo_mode}")
    print(f"autonomy         L{settings.autonomy_level}")
    print(f"x mode           {settings.x_mode}")
    print(f"database         {settings.database_url.split('@')[-1].split('?')[0]}")
    print()

    # -- the ones that must never ship ------------------------------------
    blocker(
        settings.wallet_execution_enabled,
        "wallet execution is enabled. V1 is read-only by construction; this must be False.",
    )
    blocker(
        not settings.external_content_is_untrusted,
        "EXTERNAL_CONTENT_IS_UNTRUSTED is false. External text is data, never instruction.",
    )
    blocker(
        settings.x_mode != "draft",
        f"X_MODE={settings.x_mode}. V1 never publishes automatically; it must be 'draft'.",
    )
    blocker(
        settings.autonomy_level > 1,
        f"AUTONOMY_LEVEL={settings.autonomy_level}. Levels above 1 are not implemented.",
    )

    # -- production hygiene ------------------------------------------------
    if production:
        blocker(
            not settings.admin_token,
            "ADMIN_TOKEN is unset. Approval endpoints stay disabled, which is safe but "
            "means the deployment cannot be operated. Set a long random value.",
        )
        blocker(
            bool(settings.admin_token) and len(settings.admin_token or "") < 24,
            "ADMIN_TOKEN is shorter than 24 characters.",
        )
        blocker(
            settings.database_url.startswith("sqlite"),
            "DATABASE_URL is SQLite. A container filesystem is not durable storage; "
            "point it at PostgreSQL before deploying.",
        )
        blocker(
            "*" in settings.cors_origins,
            "CORS_ORIGINS contains '*'. Name the frontend origin explicitly.",
        )
        blocker(
            any(origin.startswith("http://") for origin in settings.cors_origins),
            f"CORS_ORIGINS contains a plaintext origin: {settings.cors_origins}",
        )
        warn(
            settings.database_echo,
            "DATABASE_ECHO is on; every query will be logged.",
        )
        warn(
            settings.demo_mode,
            "DEMO_MODE is true in production. The site will serve fixtures, clearly "
            "labelled. That is a legitimate launch state — just make sure it is the "
            "one you intended.",
        )

    # -- the model layer ---------------------------------------------------
    if settings.anthropic_api_key:
        missing_roles = [
            name
            for name in ("model_writer", "model_critic")
            if not getattr(settings, name, None)
        ]
        blocker(
            bool(missing_roles),
            f"ANTHROPIC_API_KEY is set but {', '.join(r.upper() for r in missing_roles)} "
            "is unset; the agents would refuse on every call.",
        )
        blocker(
            settings.model_price_input_usd_per_mtok is None
            or settings.model_price_output_usd_per_mtok is None,
            "ANTHROPIC_API_KEY is set but MODEL_PRICE_INPUT_USD_PER_MTOK / "
            "MODEL_PRICE_OUTPUT_USD_PER_MTOK are not. The budget guard refuses to spend "
            "what it cannot measure, so no agent would ever run.",
        )
        warn(
            settings.llm_daily_budget_usd > 10,
            f"LLM_DAILY_BUDGET_USD={settings.llm_daily_budget_usd} is above the "
            "$250/month envelope in docs/COST_CONTROL.md.",
        )
    else:
        warn(
            True,
            "No ANTHROPIC_API_KEY: the writer and reviewer will refuse. Everything "
            "deterministic still runs, and /api/status says so.",
        )

    # -- the app actually builds -------------------------------------------
    try:
        app = create_app()
        routes = len(app.openapi()["paths"])
        print(f"routes           {routes}")
    except Exception as exc:
        # A failed import is the most important thing preflight can report, so it
        # is collected as a blocker rather than raised out of the check.
        BLOCKERS.append(f"the application does not build: {type(exc).__name__}: {exc}")
        routes = 0

    print()
    print("what the deployment will claim about itself:")
    for provider in describe_providers(settings):
        state = "implemented" if provider.implemented else "not implemented"
        configured = "configured" if provider.configured else "unconfigured"
        print(f"  {provider.name:<10} {state:<16} {configured}")

    print()
    for message in WARNINGS:
        print(f"[warn] {message}")
    for message in BLOCKERS:
        print(f"[STOP] {message}")

    print()
    if BLOCKERS:
        print(f"preflight: FAIL ({len(BLOCKERS)} blocking)")
        return 1
    print(f"preflight: PASS ({len(WARNINGS)} warnings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
