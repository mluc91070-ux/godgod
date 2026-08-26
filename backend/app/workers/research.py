"""Research worker.

    python -m app.workers.research        # one cycle: hypotheses, experiments, critic

Deterministic and idempotent: a question already asked is not asked again.
"""

from __future__ import annotations

import asyncio
import json

from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.models import Base
from app.services.research import run_research_cycle


async def main() -> int:
    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        report = await run_research_cycle(session)
        print(json.dumps(report.as_dict(), indent=2))

    await dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
