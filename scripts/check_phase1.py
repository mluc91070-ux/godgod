"""PHASE 1 gate.

Verifies the things PHASE 1 promised, and nothing more. Prints a plain
report and exits non-zero on the first broken promise.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

REQUIRED_TABLES = {
    "tokens",
    "token_snapshots",
    "wallets",
    "wallet_clusters",
    "social_accounts",
    "social_posts",
    "observations",
    "anomalies",
    "hypotheses",
    "experiments",
    "experiment_results",
    "patterns",
    "memories",
    "agents",
    "agent_runs",
    "content_drafts",
    "published_posts",
    "research_sources",
    "research_traces",
    "trace_steps",
    "system_events",
    "metrics_snapshots",
}

REQUIRED_DOCS = (
    "README.md",
    "CLAUDE.md",
    "AGENTS.md",
    "docs/ARCHITECTURE.md",
    "docs/RESEARCH_METHODOLOGY.md",
    "docs/AI_IDENTITY.md",
    "docs/SECURITY.md",
    "docs/DATA_SOURCES.md",
    "docs/DEPLOYMENT.md",
    "docs/COST_CONTROL.md",
    "docs/X_PUBLISHING.md",
)


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> int:
    from app.models import Base
    from app.services.fixtures import FIXTURE_FILES, dataset_hash, fixtures_dir

    failures = 0

    tables = set(Base.metadata.tables)
    missing = REQUIRED_TABLES - tables
    failures += not check("schema covers every PHASE 1 table", not missing, str(sorted(missing)))

    missing_fixtures = [name for name in FIXTURE_FILES if not (fixtures_dir() / name).is_file()]
    failures += not check("fixtures present", not missing_fixtures, str(missing_fixtures))
    failures += not check("dataset hash computable", len(dataset_hash()) == 64)

    missing_docs = [name for name in REQUIRED_DOCS if not (ROOT / name).is_file()]
    failures += not check("documentation present", not missing_docs, str(missing_docs))

    frontend_pages = sorted(p.parent.name for p in (ROOT / "frontend" / "app").rglob("page.tsx"))
    failures += not check("frontend routes present", len(frontend_pages) >= 12, str(frontend_pages))

    from app.main import create_app

    # Routers are resolved lazily, so the OpenAPI schema is the reliable
    # inventory of what the app actually serves.
    routes = set(create_app().openapi()["paths"])
    required_routes = {
        "/health",
        "/api/status",
        "/api/live",
        "/api/observations",
        "/api/observations/{observation_id}",
        "/api/hypotheses",
        "/api/experiments",
        "/api/memory/search",
        "/api/patterns",
        "/api/metrics",
        "/api/events",
        "/api/x/drafts",
    }
    missing_routes = required_routes - routes
    failures += not check("API surface present", not missing_routes, str(sorted(missing_routes)))

    print()
    print("PHASE 1 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
