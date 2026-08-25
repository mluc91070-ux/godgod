"""Memory over HTTP."""

from __future__ import annotations


async def _first_memory_id(client, memory_type: str = "failure") -> str:
    body = (await client.get("/api/memory", params={"type": memory_type})).json()
    return body["items"][0]["id"]


async def test_search_declares_its_method_and_that_it_is_not_semantic(client):
    body = (await client.get("/api/memory/search", params={"q": "market regime"})).json()

    assert body["vector"] is True
    assert body["semantic"] is False
    assert body["method"] == "vector-cosine/python-scan"
    assert body["embedding_model"] == "local-hashing-v1"
    assert body["truncated"] is False
    assert body["items"]


async def test_search_hits_carry_scores_in_descending_order(client):
    body = (await client.get("/api/memory/search", params={"q": "attention propagation"})).json()
    scores = [item["score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)
    assert all(-1.0 <= score <= 1.0 for score in scores)


async def test_search_can_recall_a_failure(client):
    body = (
        await client.get(
            "/api/memory/search", params={"q": "hypothesis rejected sign reversed"}
        )
    ).json()
    assert any(item["memory"]["memory_type"] == "FAILURE" for item in body["items"])


async def test_lexical_mode_is_selectable(client):
    body = (
        await client.get("/api/memory/search", params={"q": "regime", "mode": "lexical"})
    ).json()
    assert body["vector"] is False
    assert body["method"] == "lexical-substring-v1"
    assert body["embedding_model"] is None


async def test_search_returns_empty_rather_than_inventing(client):
    body = (
        await client.get("/api/memory/search", params={"q": "zzz-nothing-matches-here"})
    ).json()
    assert body["items"] == []


async def test_search_requires_a_query(client):
    assert (await client.get("/api/memory/search")).status_code == 422


async def test_search_rejects_an_unknown_mode(client):
    response = await client.get("/api/memory/search", params={"q": "x", "mode": "magic"})
    assert response.status_code == 422


async def test_memory_listing_reports_vector_state_without_shipping_vectors(client):
    body = (await client.get("/api/memory", params={"type": "failure"})).json()
    item = body["items"][0]

    assert item["has_vector"] is True
    assert item["embedding_model"] == "local-hashing-v1"
    assert "embedding" not in item, "1536 floats have no business in a browser payload"


async def test_related_excludes_the_seed(client):
    memory_id = await _first_memory_id(client)
    body = (await client.get(f"/api/memory/{memory_id}/related")).json()
    assert memory_id not in {item["memory"]["id"] for item in body["items"]}


async def test_cluster_starts_from_the_seed(client):
    memory_id = await _first_memory_id(client)
    body = (
        await client.get(f"/api/memory/{memory_id}/cluster", params={"threshold": 0.1})
    ).json()

    assert body["seed_id"] == memory_id
    assert body["items"][0]["memory"]["id"] == memory_id
    assert body["items"][0]["score"] == 1.0
    assert body["threshold"] == 0.1


async def test_related_and_cluster_404_for_unknown_ids(client):
    assert (await client.get("/api/memory/nope/related")).status_code == 404
    assert (await client.get("/api/memory/nope/cluster")).status_code == 404


async def test_single_memory_lookup(client):
    memory_id = await _first_memory_id(client)
    body = (await client.get(f"/api/memory/{memory_id}")).json()
    assert body["id"] == memory_id
    assert (await client.get("/api/memory/nope")).status_code == 404


async def test_summary_is_a_digest_not_a_narrative(client):
    body = (await client.get("/api/memory/summary")).json()

    assert body["method"] == "deterministic-digest-v1"
    assert body["total"] == 6
    assert body["with_vectors"] == 6
    assert body["by_type"]["FAILURE"] == 1
    assert body["recent_failures"]
    assert "does not interpret" in body["note"] or "not interpret" in body["note"]
