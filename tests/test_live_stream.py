"""PHASE 9: the live event stream.

The transport must not become a place where honesty leaks: replayed history is
labelled, a quiet system produces a quiet stream, and nothing is emitted that is
not a committed row.
"""

from __future__ import annotations

import json

import pytest
import pytest_asyncio

from app.models import SystemEvent
from app.models.base import utcnow
from app.services.stream import STREAM_VERSION, comment, event_stream, frame


def parse(chunk: str) -> tuple[str | None, dict, int | None]:
    """Pull (event, data, id) out of one SSE frame."""
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


async def add_event(session, message: str, *, seq: int, event_type: str = "OBSERVATION") -> None:
    session.add(
        SystemEvent(
            seq=seq,
            event_type=event_type,
            message=message,
            level="INFO",
            occurred_at=utcnow(),
            is_demo=True,
        )
    )
    await session.commit()


@pytest_asyncio.fixture
async def quick_settings(settings):
    """Poll fast and age out fast so the tests do not sit waiting."""
    settings.stream_poll_seconds = 0.01
    settings.stream_heartbeat_seconds = 0.0
    settings.stream_max_seconds = 0.5
    settings.stream_replay_events = 5
    return settings


async def collect(stream, limit: int) -> list[str]:
    chunks: list[str] = []
    async for chunk in stream:
        chunks.append(chunk)
        if len(chunks) >= limit:
            break
    return chunks


# -- frame encoding -------------------------------------------------------


def test_frame_encodes_event_id_and_data() -> None:
    text = frame("log", {"message": "hello"}, event_id=7)
    assert text.endswith("\n\n")
    name, data, event_id = parse(text)
    assert (name, data["message"], event_id) == ("log", "hello", 7)


def test_frame_data_is_one_line_so_a_newline_cannot_split_it() -> None:
    text = frame("log", {"message": "two\nlines"})
    body = [line for line in text.splitlines() if line.startswith("data: ")]
    assert len(body) == 1
    assert json.loads(body[0][6:])["message"] == "two\nlines"


def test_comment_is_a_comment_not_an_event() -> None:
    assert comment("heartbeat cursor=3").startswith(": ")


# -- the stream -----------------------------------------------------------


async def test_stream_opens_by_declaring_what_it_will_do(session, quick_settings) -> None:
    await add_event(session, "first", seq=1)
    chunks = await collect(event_stream(quick_settings), 1)
    name, data, _ = parse(chunks[0])
    assert name == "open"
    assert data["version"] == STREAM_VERSION
    assert data["cursor"] == 1
    assert data["poll_seconds"] > 0


async def test_history_is_labelled_as_replay(session, quick_settings) -> None:
    for index in range(1, 4):
        await add_event(session, f"event {index}", seq=index)

    chunks = await collect(event_stream(quick_settings), 4)
    logs = [parse(chunk) for chunk in chunks[1:]]
    assert len(logs) == 3
    for _, data, _ in logs:
        assert data["replayed"] is True


async def test_replay_is_capped_and_ordered_oldest_first(session, quick_settings) -> None:
    for index in range(1, 11):
        await add_event(session, f"event {index}", seq=index)

    chunks = await collect(event_stream(quick_settings), 6)
    _, opened, _ = parse(chunks[0])
    assert opened["replayed"] == quick_settings.stream_replay_events

    messages = [parse(chunk)[1]["message"] for chunk in chunks[1:]]
    assert messages == [f"event {index}" for index in range(6, 11)]


async def test_a_new_row_arrives_as_a_live_frame(session, quick_settings) -> None:
    await add_event(session, "old", seq=1)
    stream = event_stream(quick_settings, after=1)

    opened = await stream.__anext__()
    assert parse(opened)[0] == "open"

    await add_event(session, "brand new", seq=2)

    name, data, event_id = parse(await stream.__anext__())
    assert name == "log"
    assert data["message"] == "brand new"
    assert data["replayed"] is False
    assert event_id == 2
    await stream.aclose()


async def test_a_cursor_never_replays_what_the_client_already_saw(
    session, quick_settings
) -> None:
    for index in range(1, 6):
        await add_event(session, f"event {index}", seq=index)

    stream = event_stream(quick_settings, after=5)
    assert parse(await stream.__anext__())[0] == "open"

    await add_event(session, "after the cursor", seq=6)
    name, data, _ = parse(await stream.__anext__())
    assert (name, data["message"]) == ("log", "after the cursor")
    await stream.aclose()


async def test_a_quiet_system_produces_a_heartbeat_not_an_event(
    session, quick_settings
) -> None:
    await add_event(session, "only one", seq=1)
    chunks = await collect(event_stream(quick_settings, after=1), 2)
    assert chunks[1].startswith(": heartbeat")


async def test_the_connection_closes_itself_and_says_why(session, quick_settings) -> None:
    quick_settings.stream_max_seconds = 0.0
    await add_event(session, "only one", seq=1)
    chunks = [chunk async for chunk in event_stream(quick_settings, after=1)]
    name, data, _ = parse(chunks[-1])
    assert name == "close"
    assert data["reason"] == "max_connection_age"
    assert data["cursor"] == 1


async def test_a_state_change_is_announced_after_the_event_that_caused_it(
    session, quick_settings
) -> None:
    await add_event(session, "observed", seq=1, event_type="OBSERVATION")
    stream = event_stream(quick_settings, after=1)
    assert parse(await stream.__anext__())[0] == "open"

    await add_event(session, "supported", seq=2, event_type="HYPOTHESIS_SUPPORTED")
    assert parse(await stream.__anext__())[0] == "log"
    name, data, _ = parse(await stream.__anext__())
    assert name == "state"
    assert data["state"] == "SUPPORTED"
    await stream.aclose()


async def test_a_disconnected_client_stops_the_stream(session, quick_settings) -> None:
    await add_event(session, "only one", seq=1)

    async def gone() -> bool:
        return True

    chunks = [
        chunk async for chunk in event_stream(quick_settings, after=1, is_disconnected=gone)
    ]
    assert len(chunks) == 1  # the open frame, then it stops


# -- the endpoint ---------------------------------------------------------


async def test_stream_endpoint_declares_the_right_content_type(
    client, quick_settings
) -> None:
    # quick_settings caps the connection at half a second, so this reads a
    # complete short-lived stream instead of hanging on a live one.
    response = await client.get("/api/live/stream?after=999999")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"].startswith("no-cache")
    assert response.headers["x-stream-version"] == STREAM_VERSION

    frames = [line for line in response.text.splitlines() if line.startswith("data: ")]
    opened = json.loads(frames[0][6:])
    assert opened["version"] == STREAM_VERSION
    closed = json.loads(frames[-1][6:])
    assert closed["reason"] == "max_connection_age"


async def test_live_snapshot_reports_streaming_as_available(client) -> None:
    body = (await client.get("/api/live")).json()
    assert body["streaming"] is True


@pytest.mark.parametrize("value", ["-1", "abc"])
async def test_the_cursor_is_validated(client, value: str) -> None:
    response = await client.get(f"/api/live/stream?after={value}")
    assert response.status_code == 422
