"""PHASE 2 gate: memory.

Checks the five memory operations exist and behave, that vectors are
reproducible, and that nothing in the stack claims to be semantic while the
embedder is lexical.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> int:
    from sqlalchemy import select

    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.models import Base, Memory
    from app.services import memory as memory_service
    from app.services.embeddings import get_embedding_provider
    from app.services.seed import seed_demo

    failures = 0
    provider = get_embedding_provider()

    for name in (
        "store_memory",
        "search_memory",
        "retrieve_related_memories",
        "get_memory_cluster",
        "summarize_memory",
    ):
        failures += not check(f"memory.{name} exists", hasattr(memory_service, name))

    failures += not check(
        "embedder is deterministic",
        provider.embed("a stable sentence") == provider.embed("a stable sentence"),
    )
    failures += not check(
        "embedder does not claim to be semantic",
        provider.semantic is False or provider.name != "local-hashing-v1",
        "a learned model may set semantic=True; the hashing one may not",
    )

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        await seed_demo(session)

        rows = (await session.scalars(select(Memory))).all()
        failures += not check("memories stored", len(rows) > 0, f"{len(rows)} rows")
        failures += not check(
            "every memory carries a vector and names its model",
            all(row.embedding and row.embedding_model == provider.name for row in rows),
        )

        result = await memory_service.search_memory(session, "market regime split")
        failures += not check("search returns ranked hits", bool(result.hits), result.method)
        failures += not check("search reports semantic honestly", result.semantic is False)

        empty = await memory_service.search_memory(session, "quantum chromodynamics lattice")
        failures += not check("search stays silent on nonsense", empty.hits == [])

        if rows:
            related = await memory_service.retrieve_related_memories(session, rows[0], limit=5)
            failures += not check(
                "related excludes the seed",
                rows[0].id not in {hit.memory.id for hit in related.hits},
            )
            cluster = await memory_service.get_memory_cluster(session, rows[0], threshold=0.1)
            failures += not check(
                "cluster starts at the seed", cluster and cluster[0].memory.id == rows[0].id
            )

        digest = await memory_service.summarize_memory(session)
        failures += not check("digest counts stored rows", digest.total == len(rows))

    await dispose_engine()

    print()
    print("PHASE 2 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
