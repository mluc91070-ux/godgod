"""Health, status and the live snapshot."""

from __future__ import annotations

import re

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
    # The phase string moves every phase; what matters is that it names one
    # rather than describing the system as finished.
    assert re.match(r"^PHASE \d+ — ", body["phase"])

    # Solana ships last. The API must not claim otherwise.
    providers = {p["name"]: p for p in body["providers"]}
    assert set(providers) == {"solana", "x", "anthropic"}
    assert providers["solana"]["implemented"] is False

    # The model and X clients exist; with nothing configured, their notes must
    # say they refuse rather than implying a live feed.
    assert providers["anthropic"]["implemented"] is True
    assert providers["anthropic"]["configured"] is False
    assert "no API key" in providers["anthropic"]["note"]

    assert providers["x"]["implemented"] is True
    assert providers["x"]["configured"] is False
    assert "no bearer token" in providers["x"]["note"]

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
