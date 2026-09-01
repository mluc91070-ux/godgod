"""Health, status and the live snapshot."""

from __future__ import annotations

from datetime import timedelta

import pytest


async def test_health_reports_database(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


async def test_root_identity(client):
    body = (await client.get("/")).json()
    assert body["name"] == "GODGOD"
    assert body["role"] == "autonomous meme researcher"


async def test_status_declares_mode_and_what_each_provider_can_do(client):
    body = (await client.get("/api/status")).json()

    assert body["mode"]["demo_mode"] is True
    assert body["mode"]["autonomy_level"] == 1
    assert body["mode"]["x_mode"] == "draft"
    assert body["mode"]["wallet_execution_enabled"] is False
    assert body["mode"]["external_content_is_untrusted"] is True
    # The phase string describes the deployment as it is. What matters is that
    # it says something concrete and is not empty — a stale or absent one is the
    # system misdescribing itself on every page.
    assert len(body["phase"]) > 20
    assert body["phase"] == body["phase"].strip()

    # Every client is implemented; none is configured here. The notes must say
    # each one refuses, rather than implying a live feed.
    providers = {p["name"]: p for p in body["providers"]}
    assert set(providers) == {"solana", "market", "launchpad", "evm", "x", "anthropic"}
    assert all(p["configured"] is False for p in providers.values())

    assert providers["solana"]["implemented"] is True
    assert "no signing path" in providers["solana"]["note"].lower()
    assert providers["market"]["implemented"] is True
    assert "MARKET_API_URL" in providers["market"]["note"]
    assert providers["anthropic"]["implemented"] is True
    assert providers["anthropic"]["configured"] is False
    assert "no API key" in providers["anthropic"]["note"]

    # Reading is removed, not switched off. `configured` is False whatever
    # credentials exist, because there is nothing left to configure — and the
    # note has to say removed rather than unconnected, which would imply a feed
    # waiting on a key.
    assert providers["x"]["implemented"] is True
    assert providers["x"]["configured"] is False
    assert "Reading is removed" in providers["x"]["note"]
    assert "no collector" in providers["x"]["note"]

    # The second chain's node. Unset here, and the note has to say that no
    # curve state is read rather than implying every token is unmigrated.
    assert providers["evm"]["implemented"] is True
    assert providers["evm"]["configured"] is False
    assert "EVM_RPC_URL is not set" in providers["evm"]["note"]
    assert "none of which can sign" in providers["evm"]["note"].lower()

    assert body["counts"]["observations"] > 0


async def test_status_describes_the_memory_subsystem(client):
    memory = (await client.get("/api/status")).json()["memory"]

    assert memory["vector_search"] is True
    assert memory["embedding_provider"] == "local"
    assert memory["embedding_model"] == "local-hashing-v1"
    assert memory["embedding_dim"] == 1536
    assert memory["backend"] == "python-scan", "pgvector is only used on PostgreSQL"
    assert memory["semantic"] is False, "the local embedder is lexical"


async def test_live_snapshot_reflects_stored_events(client):
    body = (await client.get("/api/live")).json()

    assert body["state"] in {
        "IDLE",
        "OBSERVING",
        "ANALYZING",
        "HYPOTHESIZING",
        "TESTING",
        "REJECTED",
        "SUPPORTED",
        "LEARNING",
    }
    assert body["is_demo"] is True
    assert body["streaming"] is True, "GET /api/live/stream is served on this build"
    assert body["current_observation"]["summary"]
    assert 0.0 <= body["activity"] <= 1.0


async def test_events_are_ordered_newest_first(client):
    body = (await client.get("/api/events", params={"limit": 5})).json()
    assert body["total"] >= 10
    timestamps = [item["occurred_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_events_filter_by_type(client):
    body = (await client.get("/api/events", params={"event_type": "ANOMALY"})).json()
    assert body["items"]
    assert {item["event_type"] for item in body["items"]} == {"ANOMALY"}


async def test_metrics_expose_outcome_breakdown(client):
    body = (await client.get("/api/metrics")).json()
    counts = body["counts"]
    assert counts["results_by_outcome"]["rejected"] == 1
    assert counts["hypotheses_by_status"]["rejected"] == 1
    assert counts["hypotheses_by_status"]["supported"] == 0


async def test_agent_roster_is_not_claimed_as_running(client):
    agents = (await client.get("/api/agents")).json()
    assert {a["name"] for a in agents} == {
        "observer",
        "researcher",
        "data_scientist",
        "critic",
        "writer",
        "reviewer",
    }
    from app.agents import IMPLEMENTED_AGENTS

    for agent in agents:
        assert agent["implemented"] is (agent["name"] in IMPLEMENTED_AGENTS), agent["name"]
    assert all(a["allowed_tools"] for a in agents), "each agent declares limited tools"


@pytest.mark.parametrize("path", ["/api/observations", "/api/hypotheses", "/api/experiments"])
async def test_pagination_envelope(client, path):
    body = (await client.get(path, params={"limit": 1, "offset": 0})).json()
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) <= 1
    assert body["is_demo"] is True


async def test_status_reports_live_collection_apart_from_the_demo_data(client):
    """The collectors run while the site still serves fixtures. Their counts
    must be visible and must not include a single demo row."""
    collection = (await client.get("/api/status")).json()["collection"]

    assert collection["observing_live"] is False, "demo mode is on in the test harness"
    assert collection["live_tokens"] == 0
    assert collection["live_snapshots"] == 0
    assert collection["needed_to_observe"] > 1, "one measurement is never a trend"
    assert collection["deepest_history"] == 0


async def test_live_counts_exclude_demo_rows(client, session):
    """The seeded fixtures are demo rows; none may be counted as live."""
    from sqlalchemy import func, select

    from app.models import Token

    seeded = await session.scalar(select(func.count()).select_from(Token))
    assert seeded > 0, "the harness seeded demo tokens"

    collection = (await client.get("/api/status")).json()["collection"]
    assert collection["live_tokens"] == 0


# -- /api/status cost -----------------------------------------------------
#
# This endpoint is on the critical path of every page: the honesty strip, the
# footer and several pages all read it. It used to load every live token as an
# ORM object and then run one COUNT(*) per token — at 1,035 tokens in
# production that was 1,036 round trips and about two seconds, paid on every
# visit. The number of queries must not depend on how many tokens exist.


async def test_status_does_not_query_once_per_token(client, session) -> None:
    from sqlalchemy import event

    from app.db.session import get_engine
    from app.models import Token, TokenSnapshot
    from app.models.base import utcnow

    async def add_tokens(count: int, *, offset: int) -> None:
        for index in range(count):
            token = Token(
                address=f"COSTTOKEN{offset + index}",
                chain="solana",
                source="promotion-feed",
                is_demo=False,
            )
            session.add(token)
            await session.flush()
            # Differing depths, so `deepest_history` has something to be wrong about.
            for step in range(index + 1):
                session.add(
                    TokenSnapshot(
                        token_id=token.id,
                        observed_at=utcnow() + timedelta(minutes=15 * step),
                        liquidity_usd=1000.0,
                        source="test",
                        is_demo=False,
                    )
                )
        await session.commit()

    def counter(store: list[int]):
        def listener(conn, cursor, statement, parameters, context, executemany):
            store[0] += 1

        return listener

    async def measure() -> int:
        box = [0]
        listener = counter(box)
        engine = get_engine().sync_engine
        event.listen(engine, "before_cursor_execute", listener)
        try:
            response = await client.get("/api/status")
            assert response.status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        return box[0]

    await add_tokens(3, offset=0)
    few = await measure()

    await add_tokens(12, offset=100)
    many = await measure()

    assert many == few, (
        f"{few} queries for 3 tokens and {many} for 15: the cost of /api/status "
        "grows with the number of tokens"
    )


async def test_deepest_history_is_the_deepest_series(client, session) -> None:
    """The aggregate has to agree with what the loop used to compute."""
    from app.models import Token, TokenSnapshot
    from app.models.base import utcnow

    for depth in (2, 7, 4):
        token = Token(
            address=f"DEPTH{depth}", chain="solana", source="promotion-feed", is_demo=False
        )
        session.add(token)
        await session.flush()
        for step in range(depth):
            session.add(
                TokenSnapshot(
                    token_id=token.id,
                    observed_at=utcnow() + timedelta(minutes=15 * step),
                    liquidity_usd=1000.0,
                    source="test",
                    is_demo=False,
                )
            )
    await session.commit()

    body = (await client.get("/api/status")).json()
    assert body["collection"]["deepest_history"] == 7
