"""Memory access. PHASE 1 is lexical only and must say so."""

from __future__ import annotations


async def test_search_is_declared_non_semantic(client):
    body = (await client.get("/api/memory/search", params={"q": "regime"})).json()
    assert body["semantic"] is False
    assert body["method"] == "lexical-substring-v1"
    assert body["items"], "the regime-split memory should match"


async def test_search_can_recall_a_failure(client):
    body = (await client.get("/api/memory/search", params={"q": "rejected"})).json()
    assert any(item["memory_type"] == "FAILURE" for item in body["items"])


async def test_search_filters_by_type(client):
    body = (
        await client.get("/api/memory/search", params={"q": "propagation", "type": "narrative"})
    ).json()
    assert {item["memory_type"] for item in body["items"]} == {"NARRATIVE"}


async def test_search_returns_empty_rather_than_inventing(client):
    body = (await client.get("/api/memory/search", params={"q": "zzz-nothing-matches"})).json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_search_requires_a_query(client):
    assert (await client.get("/api/memory/search")).status_code == 422


async def test_memory_listing_by_type(client):
    body = (await client.get("/api/memory", params={"type": "failure"})).json()
    assert body["total"] == 1
    assert body["items"][0]["memory_type"] == "FAILURE"
