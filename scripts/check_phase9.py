"""PHASE 9 gate: the live stream.

Opens a real stream against the database, writes an event underneath it, and
checks that the frame arrives with the right cursor — and that history is
labelled as history.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


def parse(chunk: str) -> tuple[str | None, dict, int | None]:
    name: str | None = None
    event_id: int | None = None
    data = "{}"
    for line in chunk.strip().splitlines():
        if line.startswith("event: "):
            name = line[7:]
        elif line.startswith("data: "):
            data = line[6:]
        elif line.startswith("id: "):
            event_id = int(line[4:])
    return name, json.loads(data), event_id


async def main() -> int:
    from sqlalchemy import func, select

    from app.core.config import get_settings
    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.main import create_app
    from app.models import Base, SystemEvent
    from app.models.base import utcnow
    from app.services.stream import STREAM_VERSION, event_stream

    failures = 0
    settings = get_settings()
    settings.stream_poll_seconds = 0.02
    settings.stream_heartbeat_seconds = 0.1
    settings.stream_max_seconds = 5.0

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    paths = create_app().openapi()["paths"]
    failures += not check("/api/live/stream is routed", "/api/live/stream" in paths)

    async with get_sessionmaker()() as session:
        highest = int(await session.scalar(select(func.max(SystemEvent.seq))) or 0)
        for offset in range(1, 4):
            session.add(
                SystemEvent(
                    seq=highest + offset,
                    event_type="OBSERVATION",
                    message=f"gate history {offset}",
                    level="INFO",
                    occurred_at=utcnow(),
                    is_demo=True,
                )
            )
        await session.commit()
        cursor = highest + 3

    # -- history is replayed and labelled ---------------------------------
    stream = event_stream(settings)
    name, opened, _ = parse(await stream.__anext__())
    failures += not check(
        "stream opens by declaring itself",
        name == "open" and opened["version"] == STREAM_VERSION,
        f"cursor={opened.get('cursor')}",
    )
    name, first, _ = parse(await stream.__anext__())
    failures += not check(
        "history is marked as replay", name == "log" and first["replayed"] is True
    )
    await stream.aclose()

    # -- a row written underneath the stream arrives live -----------------
    stream = event_stream(settings, after=cursor)
    parse(await stream.__anext__())

    async with get_sessionmaker()() as session:
        session.add(
            SystemEvent(
                seq=cursor + 1,
                event_type="ANOMALY",
                message="gate live row",
                level="INFO",
                occurred_at=utcnow(),
                is_demo=True,
            )
        )
        await session.commit()

    frames = []
    while len(frames) < 4:
        chunk = await asyncio.wait_for(stream.__anext__(), timeout=3.0)
        if chunk.startswith(":"):
            continue
        frames.append(parse(chunk))
        if frames[-1][0] == "log":
            break

    name, payload, event_id = frames[-1]
    failures += not check(
        "a new row arrives as a live frame",
        name == "log" and payload["message"] == "gate live row",
    )
    failures += not check("the live frame is not marked replay", payload["replayed"] is False)
    failures += not check(
        "the frame carries a resumable cursor", event_id == cursor + 1, f"id={event_id}"
    )
    await stream.aclose()

    # -- a cursor past the end replays nothing ----------------------------
    stream = event_stream(settings, after=10**9)
    name, opened, _ = parse(await stream.__anext__())
    failures += not check("a future cursor replays nothing", opened["replayed"] == 0)
    await stream.aclose()

    # -- the connection ages out rather than living forever ---------------
    settings.stream_max_seconds = 0.0
    chunks = [chunk async for chunk in event_stream(settings, after=10**9)]
    name, closed, _ = parse(chunks[-1])
    failures += not check(
        "the connection closes itself and says why",
        name == "close" and closed["reason"] == "max_connection_age",
    )

    await dispose_engine()
    print()
    print("PHASE 9 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
