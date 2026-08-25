"""Re-embed stored memories.

Needed whenever the embedder changes: vectors produced by a different model
are not comparable, and `search_memory` deliberately ignores rows whose
`embedding_model` does not match the active provider — so a model switch
silently shrinks memory until this runs.

    python scripts/backfill_embeddings.py            # only rows that need it
    python scripts/backfill_embeddings.py --all      # re-embed everything
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import or_, select

from app.db.session import dispose_engine, get_sessionmaker
from app.models import Memory
from app.services.embeddings import content_hash, get_embedding_provider


async def main(rebuild_all: bool) -> int:
    provider = get_embedding_provider()
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        stmt = select(Memory)
        if not rebuild_all:
            stmt = stmt.where(
                or_(
                    Memory.embedding.is_(None),
                    Memory.embedding_model.is_(None),
                    Memory.embedding_model != provider.name,
                )
            )
        rows = (await session.scalars(stmt)).all()

        for row in rows:
            text = f"{row.summary}\n{row.content}" if row.summary else row.content
            row.embedding = provider.embed(text)
            row.embedding_model = provider.name
            row.content_hash = row.content_hash or content_hash(row.content)

        await session.commit()

    print(f"re-embedded {len(rows)} memories with {provider.name} (dim {provider.dim})")
    await dispose_engine()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill memory embeddings")
    parser.add_argument("--all", action="store_true", help="re-embed every row")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.all)))
