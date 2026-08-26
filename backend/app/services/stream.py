"""The live event stream (PHASE 9).

Server-sent events over the rows the pipeline and the research cycle already
commit. There is no separate message bus: the database is the single source of
truth, and the stream is a cursor over `system_events.seq`, which is assigned in
insertion order.

Two honesty constraints:

- The stream reports what was **written**, never what is *about* to happen. A
  quiet stream means the system is quiet, not that the connection is broken —
  which is why the heartbeat carries the cursor and the connection says when it
  is going to close.
- Replayed history is labelled as replay. A demo database holds events with past
  timestamps; showing them as if they had just happened would be a lie told by
  the transport.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.core.config import Settings
from app.db.session import get_sessionmaker
from app.models import SystemEvent
from app.models.base import utcnow
from app.services.state import get_state

STREAM_VERSION = "sse-v1"


def frame(event: str, data: dict[str, Any], *, event_id: int | None = None) -> str:
    """One SSE frame. `id:` lets a reconnect resume from where it stopped."""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, separators=(',', ':'), default=str)}")
    return "\n".join(lines) + "\n\n"


def comment(text: str) -> str:
    """A comment frame. Keeps proxies open without firing a client handler."""
    return f": {text}\n\n"


@dataclass
class EventPayload:
    id: str
    seq: int | None
    event_type: str
    message: str
    level: str
    ref_type: str | None
    ref_id: str | None
    occurred_at: str
    is_demo: bool
    replayed: bool

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


def _payload(row: SystemEvent, *, replayed: bool) -> EventPayload:
    return EventPayload(
        id=row.id,
        seq=row.seq,
        event_type=row.event_type,
        message=row.message,
        level=row.level,
        ref_type=row.ref_type,
        ref_id=row.ref_id,
        occurred_at=row.occurred_at.isoformat(),
        is_demo=bool(row.is_demo),
        replayed=replayed,
    )


async def _fetch_after(cursor: int, limit: int) -> list[SystemEvent]:
    async with get_sessionmaker()() as session:
        return list(
            (
                await session.scalars(
                    select(SystemEvent)
                    .where(SystemEvent.seq > cursor)
                    .order_by(SystemEvent.seq)
                    .limit(limit)
                )
            ).all()
        )


async def _fetch_tail(limit: int) -> list[SystemEvent]:
    async with get_sessionmaker()() as session:
        rows = (
            await session.scalars(
                select(SystemEvent)
                .where(SystemEvent.seq.is_not(None))
                .order_by(SystemEvent.seq.desc())
                .limit(limit)
            )
        ).all()
    return list(reversed(rows))


async def _current_state() -> str:
    async with get_sessionmaker()() as session:
        return str(await get_state(session))


async def event_stream(
    settings: Settings,
    *,
    after: int | None = None,
    is_disconnected: Any = None,
) -> AsyncIterator[str]:
    """Yield SSE frames until the client leaves or the connection ages out.

    `after` resumes from a cursor (the browser sends it back as Last-Event-ID);
    without one the tail of the log is replayed so a fresh tab has context.

    Each connection opens a short-lived session per poll rather than holding one
    for its whole lifetime: an idle transaction pinned for fifteen minutes is how
    a connection pool dies.
    """
    poll = max(0.05, settings.stream_poll_seconds)
    deadline = utcnow().timestamp() + settings.stream_max_seconds

    if after is None:
        history = await _fetch_tail(settings.stream_replay_events)
        cursor = history[-1].seq if history else 0
    else:
        history = []
        cursor = after

    state = await _current_state()
    yield frame(
        "open",
        {
            "version": STREAM_VERSION,
            "cursor": cursor,
            "state": state,
            "replayed": len(history),
            "poll_seconds": poll,
            "closes_after_seconds": settings.stream_max_seconds,
            "note": "events are database rows; a quiet stream means a quiet system",
        },
    )

    for row in history:
        yield frame("log", _payload(row, replayed=True).as_dict(), event_id=row.seq)

    last_beat = utcnow().timestamp()
    while True:
        if is_disconnected is not None and await is_disconnected():
            return

        now = utcnow().timestamp()
        if now >= deadline:
            yield frame("close", {"reason": "max_connection_age", "cursor": cursor})
            return

        rows = await _fetch_after(cursor, limit=200)
        for row in rows:
            cursor = row.seq or cursor
            yield frame("log", _payload(row, replayed=False).as_dict(), event_id=row.seq)

        if rows:
            fresh = await _current_state()
            if fresh != state:
                state = fresh
                yield frame("state", {"state": state, "cursor": cursor})
            last_beat = now
        elif now - last_beat >= settings.stream_heartbeat_seconds:
            last_beat = now
            yield comment(f"heartbeat cursor={cursor}")

        await asyncio.sleep(poll)
