"""Observation worker.

    python -m app.workers.observe              # one cycle at the newest measurement
    python -m app.workers.observe --backfill   # walk the series hour by hour

Deterministic and idempotent: the cooldown window means re-running over the
same period does not duplicate anomalies.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.models import Base
from app.services.observation import ObservationPipeline, run_backfill


async def _ensure_schema() -> None:
    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def main(backfill: bool) -> int:
    await _ensure_schema()
    async with get_sessionmaker()() as session:
        if backfill:
            reports = await run_backfill(session)
            totals = {
                "cycles": len(reports),
                "observations": sum(report.observations_created for report in reports),
                "anomalies": sum(report.anomalies_created for report in reports),
                "memories": sum(report.memories_written for report in reports),
                "dropped": sum(sum(report.dropped.values()) for report in reports),
                "llm_calls": 0,
            }
            print(json.dumps(totals, indent=2))
        else:
            report = await ObservationPipeline().run(session)
            print(json.dumps(report.as_dict(), indent=2))

    await dispose_engine()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the GODGOD observation pipeline")
    parser.add_argument(
        "--backfill", action="store_true", help="replay the whole series hour by hour"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.backfill)))
