"""Draft approval, the publishing block, and the token page."""

from __future__ import annotations


async def _draft_by_type(client, content_type: str) -> dict:
    body = (await client.get("/api/x/drafts", params={"limit": 100})).json()
    return next(item for item in body["items"] if item["content_type"] == content_type)


async def test_drafts_show_the_reviewer_rejection(client):
    body = (await client.get("/api/x/drafts", params={"status": "REJECTED"})).json()
    assert body["total"] == 1
    rejected = body["items"][0]
    assert rejected["reviewer_verdict"] == "FAIL"
    assert rejected["rejection_reason"]


async def test_approval_requires_the_admin_token(client):
    draft = await _draft_by_type(client, "OBSERVATION")
    response = await client.post(
        f"/api/x/drafts/{draft['id']}/approve", json={"actor": "nobody"}
    )
    assert response.status_code == 401


async def test_approval_records_who_approved(client, admin_headers):
    draft = await _draft_by_type(client, "OBSERVATION")
    response = await client.post(
        f"/api/x/drafts/{draft['id']}/approve",
        json={"actor": "operator", "notes": "matches observation #041"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["approved_by"] == "operator"
    assert body["approved_at"]


async def test_unsourced_draft_cannot_be_approved(client, admin_headers, session):
    from sqlalchemy import select

    from app.models import ContentDraft

    draft = await session.scalar(select(ContentDraft).limit(1))
    draft.source_kind = None
    await session.commit()

    response = await client.post(
        f"/api/x/drafts/{draft.id}/approve", json={"actor": "operator"}, headers=admin_headers
    )
    assert response.status_code == 422


async def test_rejection_stores_a_reason(client, admin_headers):
    draft = await _draft_by_type(client, "THOUGHT")
    body = (
        await client.post(
            f"/api/x/drafts/{draft['id']}/reject",
            json={"actor": "operator", "notes": "too vague"},
            headers=admin_headers,
        )
    ).json()
    assert body["status"] == "REJECTED"
    assert body["rejection_reason"] == "too vague"


async def test_publishing_is_refused_unless_the_deployment_opts_in(client, admin_headers):
    """The refusal must say the deployment has not opted in, not that the code
    is missing — those are different facts and only one of them is true now."""
    draft = await _draft_by_type(client, "FAILURE")
    response = await client.post(
        f"/api/x/drafts/{draft['id']}/publish", headers=admin_headers
    )
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["x_mode"] == "draft"
    assert "X_MODE=publish" in detail["note"]
    assert "not implemented" not in detail["note"].lower()


async def test_token_page_shows_unknowns_as_null(client):
    body = (await client.get("/api/tokens")).json()
    placeholder = next(item for item in body["items"] if item["symbol"] == "GODGOD")
    assert placeholder["market_cap_usd"] is None
    assert placeholder["holders"] is None
    assert placeholder["is_demo"] is True


async def test_token_lookup_by_address(client):
    body = (await client.get("/api/tokens/DEMO1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")).json()
    assert body["symbol"] == "ALPHA"
    assert (await client.get("/api/tokens/not-a-token")).status_code == 404
