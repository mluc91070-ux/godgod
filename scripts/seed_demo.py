"""Seed the database with the demo fixtures.

Usage (from the repository root, with the backend venv active):

    python scripts/seed_demo.py            # seed if empty
    python scripts/seed_demo.py --force    # replace existing demo rows
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.models import Base
from app.services.seed import seed_demo


async def main(force: bool, create_schema: bool) -> int:
    if create_schema:
        engine = get_engine()
        if engine.url.get_backend_name() != "sqlite":
            print("refusing to create schema on a non-sqlite database; run alembic instead")
            return 2
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        result = await seed_demo(session, force=force)

    print(json.dumps(result, indent=2))
    await dispose_engine()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed GODGOD demo fixtures")
    parser.add_argument("--force", action="store_true", help="delete existing demo rows first")
    parser.add_argument(
        "--no-create-schema",
        action="store_true",
        help="skip create_all (use when the schema comes from alembic)",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.force, not args.no_create_schema)))
