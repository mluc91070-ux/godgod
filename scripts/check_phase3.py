"""PHASE 3 gate: observation.

Runs the pipeline against the synthetic dataset and checks that it finds
every planted pattern, stays silent on the control, and calls no model.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

EXPECTED = {
    "SURGE": "VOLUME_ACCELERATION",
    "DRAIN": "LIQUIDITY_CHANGE",
    "WHALE": "WALLET_CONCENTRATION_CHANGE",
    "BUZZ": "SOCIAL_ONCHAIN_DIVERGENCE",
    "OLD": "TOKEN_SURVIVAL_ANOMALY",
    "narrative": "NARRATIVE_ACCELERATION",
}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> int:
    from sqlalchemy import func, select

    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.models import AgentRun, Anomaly, Base, Observation, TokenSnapshot
    from app.providers.source import FixtureObservationSource
    from app.services.observation import run_backfill
    from app.services.observation.detectors import DETECTOR_NAMES
    from app.services.observation.pipeline import PIPELINE_RUN_NAME

    failures = 0

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        reports = await run_backfill(session, source=FixtureObservationSource())
        failures += not check("pipeline ran", bool(reports), f"{len(reports)} cycles")

        rows = (
            await session.execute(
                select(Observation.summary, Anomaly.anomaly_type).join(
                    Anomaly, Anomaly.observation_id == Observation.id
                )
            )
        ).all()
        found: dict[str, set[str]] = {}
        for summary, anomaly_type in rows:
            found.setdefault(summary.split(":")[0].strip(), set()).add(anomaly_type)

        for subject, anomaly_type in EXPECTED.items():
            failures += not check(
                f"{subject}: {anomaly_type} detected", anomaly_type in found.get(subject, set())
            )

        failures += not check(
            "control token stays silent", "FLAT" not in found, "FLAT must fire nothing"
        )

        observations = (await session.scalars(select(Observation))).all()
        failures += not check(
            "no observation claims model review",
            all(row.llm_reviewed is False for row in observations),
        )
        failures += not check(
            "every observation is scored",
            all(
                row.novelty_score is not None
                and row.importance is not None
                and row.confidence is not None
                for row in observations
            ),
        )

        anomalies = (await session.scalars(select(Anomaly))).all()
        failures += not check(
            "every anomaly names a versioned detector and scores above zero",
            all(a.detector.endswith("-v1") and (a.score or 0) > 0 for a in anomalies),
        )
        failures += not check(
            "every anomaly records its thresholds",
            all("thresholds" in (a.baseline or {}) for a in anomalies),
        )

        snapshots = await session.scalar(select(func.count()).select_from(TokenSnapshot))
        failures += not check(
            "measurements ingested exactly once", snapshots == 144, f"{snapshots} rows"
        )

        runs = (
            await session.scalars(
                select(AgentRun).where(AgentRun.agent_name == PIPELINE_RUN_NAME)
            )
        ).all()
        failures += not check(
            "runs recorded with no model and zero cost",
            bool(runs) and all(r.model is None and r.estimated_cost_usd == 0.0 for r in runs),
        )

        dropped = sum(sum(report.dropped.values()) for report in reports)
        created = sum(report.observations_created for report in reports)
        failures += not check(
            "cheap filter rejects more than it passes",
            dropped > created,
            f"{dropped} dropped vs {created} recorded",
        )

        failures += not check("detector roster complete", len(DETECTOR_NAMES) == 10)

    await dispose_engine()
    print()
    print("PHASE 3 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
