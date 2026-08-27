"""PHASE 10 gate: the public research pages.

The pages are server-rendered from the API, so this gate checks the contract
they depend on: every public route has data behind it, every experiment and
hypothesis is reachable by a stable URL, rejections and inconclusives are listed
rather than quietly dropped, and nothing renders a claim the API did not make.

It does not start Node. What it proves is that if the pages render, they render
real rows — `npm run build` and `npm run typecheck` cover the rest.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

FRONTEND = ROOT / "frontend"

PAGES: dict[str, tuple[str, ...]] = {
    "/": ("/api/live", "/api/status"),
    "/terminal": ("/api/events", "/api/live/stream"),
    "/observe": ("/api/observations", "/api/anomalies"),
    "/memory": ("/api/memory", "/api/memory/summary"),
    "/hypotheses": ("/api/hypotheses",),
    "/experiments": ("/api/experiments",),
    "/findings": ("/api/results",),
    # Static pages: they explain the system and read no endpoint.
    "/research": (),
    "/about": (),
    "/docs": (),
    "/patterns": ("/api/patterns",),
    "/agents": ("/api/agents",),
    "/data": ("/api/sources", "/api/metrics"),
}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.main import create_app
    from app.models import Base
    from app.providers.source import FixtureObservationSource
    from app.services.observation import run_backfill
    from app.services.research import run_research_cycle
    from app.services.seed import seed_demo

    failures = 0

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        await seed_demo(session)
    async with get_sessionmaker()() as session:
        await run_backfill(session, source=FixtureObservationSource())
    async with get_sessionmaker()() as session:
        await run_research_cycle(session)

    app = create_app()
    routed = set(app.openapi()["paths"])

    # -- every page has a file, and every endpoint it reads is routed ------
    for page, endpoints in PAGES.items():
        relative = "app/page.tsx" if page == "/" else f"app{page}/page.tsx"
        failures += not check(f"{page} exists", (FRONTEND / relative).exists(), relative)
        for endpoint in endpoints:
            failures += not check(f"{page} reads {endpoint}", endpoint in routed)

    for detail in ("app/experiments/[id]/page.tsx", "app/hypotheses/[id]/page.tsx",
                   "app/memory/[id]/page.tsx"):
        failures += not check(f"{detail} exists", (FRONTEND / detail).exists())

    # -- every page is reachable from the nav -----------------------------
    # Read the hrefs themselves rather than the route arrays: the home link
    # lives on the logo, and a check that only sees array literals reports a
    # page as unreachable while it is sitting in the top-left corner.
    nav = (FRONTEND / "components/Nav.tsx").read_text(encoding="utf-8")
    linked = set(re.findall(r'"(/[^"]*)"', nav)) | set(re.findall(r'href="(/[^"]*)"', nav))
    missing = set(PAGES) - linked
    failures += not check("every page is in the nav", not missing, ", ".join(sorted(missing)))

    # -- the data behind them ---------------------------------------------
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://gate") as client:
        status = (await client.get("/api/status")).json()
        failures += not check(
            "status reports the phase and both engines",
            status["pipeline"]["implemented"] and status["research"]["implemented"],
            status["phase"],
        )
        failures += not check(
            "status admits no model is in the loop",
            status["pipeline"]["llm_in_loop"] is False
            and status["research"]["llm_in_loop"] is False,
        )

        for endpoint in sorted({item for group in PAGES.values() for item in group}):
            if endpoint.endswith("/stream"):
                continue
            response = await client.get(endpoint)
            failures += not check(f"{endpoint} answers", response.status_code == 200)

        hypotheses = (await client.get("/api/hypotheses?limit=200")).json()["items"]
        failures += not check("hypotheses exist to publish", bool(hypotheses))
        for hypothesis in hypotheses:
            failures += not check(
                f"hypothesis {hypothesis['seq']} states how it can be wrong",
                bool(hypothesis["falsification_condition"]),
            )
            detail = await client.get(f"/api/hypotheses/{hypothesis['id']}")
            if detail.status_code != 200:
                failures += not check(f"hypothesis {hypothesis['seq']} has a page", False)

        experiments = (await client.get("/api/experiments?limit=200")).json()["items"]
        failures += not check("experiments exist to publish", bool(experiments))
        for experiment in experiments:
            detail = (await client.get(f"/api/experiments/{experiment['id']}")).json()
            failures += not check(
                f"experiment {experiment['seq']} publishes its method and dataset",
                bool(detail["method"]) and bool(detail["dataset_hash"]),
            )
            for result in detail["results"]:
                failures += not check(
                    f"experiment {experiment['seq']} publishes its limitations",
                    bool(result["limitations"]) or bool(detail["limitations"]),
                )

        results = (await client.get("/api/results?limit=200")).json()
        failures += not check("results are listed", results["total"] > 0, f"{results['total']}")
        failures += not check(
            "every listed result carries a critic verdict and a summary",
            all(item["critic_verdict"] and item["summary"] for item in results["items"]),
        )
        outcomes = {item["outcome"] for item in results["items"]}
        failures += not check(
            "no outcome is filtered out of the public record",
            outcomes <= {"SUPPORTED", "REJECTED", "INCONCLUSIVE"},
            ", ".join(sorted(outcomes)),
        )
        for outcome in sorted(outcomes):
            filtered = (await client.get(f"/api/results?outcome={outcome}")).json()
            failures += not check(
                f"results can be filtered to {outcome.lower()}",
                filtered["total"] > 0
                and all(item["outcome"] == outcome for item in filtered["items"]),
            )

        listed = {item["id"] for item in results["items"]}
        recorded: set[str] = set()
        for experiment in experiments:
            detail = (await client.get(f"/api/experiments/{experiment['id']}")).json()
            recorded.update(item["id"] for item in detail["results"])
        failures += not check(
            "nothing recorded is missing from the public listing", recorded <= listed
        )

        drafts = (await client.get("/api/x/drafts")).json()
        failures += not check(
            "no draft claims to have been published",
            all(item["status"] != "PUBLISHED" for item in drafts["items"]),
        )

    await dispose_engine()
    print()
    print("PHASE 10 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
