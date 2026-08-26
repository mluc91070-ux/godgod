"""Publishing to X: the gates between a result and a post.

Nothing here touches the network. What is tested is the set of refusals,
because every one of them is the difference between a research account and a
bot that eventually says something it cannot support.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.enums import DraftStatus
from app.models import AgentRun, ContentDraft, ExperimentResult, PublishedPost
from app.providers.base import ProviderNotConfigured
from app.providers.oauth1 import OAuth1Credentials, sign, signature_base
from app.providers.source import FixtureObservationSource
from app.providers.x import HttpXProvider, PublishingDisabled
from app.services.observation import run_backfill
from app.services.publish import PUBLISH_RUN_NAME, publish_next
from app.services.research import run_research_cycle


class FakeX:
    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.posted: list[str] = []

    async def create_post(self, text: str, reply_to: str | None = None):
        if self.raises:
            raise self.raises
        self.posted.append(text)
        return {"id": "1934567890123456789", "text": text}


@pytest_asyncio.fixture
async def publishing(settings):
    settings.x_mode = "publish"
    settings.x_api_key = "ck"
    settings.x_api_secret = "cs"
    settings.x_access_token = "at"
    settings.x_access_token_secret = "ats"
    settings.x_min_minutes_between_posts = 45
    settings.autonomy_level = 1
    return settings


@pytest_asyncio.fixture
async def approved_draft(session, settings):
    """A real result, a draft describing it, approved by a human."""
    await run_backfill(session, source=FixtureObservationSource(), settings=settings)
    await run_research_cycle(session, settings=settings)
    result = await session.scalar(select(ExperimentResult).limit(1))

    draft = ContentDraft(
        content_type="RESULT",
        body=f"hypothesis: {result.outcome.lower()}. i can't tell yet.",
        status=str(DraftStatus.APPROVED),
        source_kind="experiment_result",
        source_id=result.id,
        approved_at=datetime.now(UTC),
        approved_by="operator",
        is_demo=False,
    )
    session.add(draft)
    await session.flush()
    return draft


# -- OAuth 1.0a -----------------------------------------------------------


def test_the_signature_base_matches_the_rfc_example() -> None:
    """RFC 5849 §3.4.1. Getting this wrong means every write returns 401 with
    no indication of why, so the whole string is checked rather than a prefix.

    The double encoding is the part that is easy to get wrong: a value of
    `=%3D` normalises to `%3D%253D`, and the normalised string is then encoded
    again as a whole, giving `b5%3D%253D%25253D`.
    """
    base = signature_base(
        "POST",
        "http://example.com/request",
        {"b5": "=%3D", "a3": "a", "c@": "", "a2": "r b", "c2": ""},
    )
    assert base == (
        "POST&http%3A%2F%2Fexample.com%2Frequest&"
        "a2%3Dr%2520b%26a3%3Da%26b5%3D%253D%25253D%26c%2540%3D%26c2%3D"
    )


def test_the_header_carries_every_required_field() -> None:
    header = sign(
        OAuth1Credentials("ck", "cs", "at", "ats"),
        "POST",
        "https://api.x.com/2/tweets",
        nonce="abc",
        timestamp="1700000000",
    )
    for field in (
        "oauth_consumer_key",
        "oauth_nonce",
        "oauth_signature",
        "oauth_signature_method",
        "oauth_timestamp",
        "oauth_token",
        "oauth_version",
    ):
        assert field in header
    assert 'oauth_signature_method="HMAC-SHA1"' in header


def test_the_same_request_signs_the_same_way() -> None:
    args = ("POST", "https://api.x.com/2/tweets")
    kwargs = {"nonce": "n", "timestamp": "1"}
    creds = OAuth1Credentials("ck", "cs", "at", "ats")
    assert sign(creds, *args, **kwargs) == sign(creds, *args, **kwargs)


def test_a_different_secret_signs_differently() -> None:
    kwargs = {"nonce": "n", "timestamp": "1"}
    a = sign(OAuth1Credentials("ck", "cs", "at", "ats"), "POST", "https://x", **kwargs)
    b = sign(OAuth1Credentials("ck", "OTHER", "at", "ats"), "POST", "https://x", **kwargs)
    assert a != b


def test_incomplete_credentials_are_recognised() -> None:
    assert OAuth1Credentials("a", "b", "c", "d").complete
    assert not OAuth1Credentials("a", "b", "c", "").complete


async def test_posting_needs_user_context_not_the_bearer_token(publishing) -> None:
    """The expensive thing to learn late: a valid bearer token on a paid tier
    still cannot write."""
    publishing.x_bearer_token = "bearer-only"
    publishing.x_api_key = None
    provider = HttpXProvider(publishing)
    with pytest.raises(ProviderNotConfigured, match="X_API_KEY"):
        await provider.create_post("anything")


# -- the gates ------------------------------------------------------------


async def test_nothing_publishes_while_the_mode_is_draft(
    session, settings, approved_draft
) -> None:
    settings.x_mode = "draft"
    x = FakeX()
    outcome = await publish_next(session, settings=settings, provider=x, commit=False)
    assert outcome.published is False
    assert "X_MODE=draft" in outcome.reason
    assert x.posted == []


async def test_a_configured_deployment_publishes_an_approved_draft(
    session, publishing, approved_draft
) -> None:
    x = FakeX()
    outcome = await publish_next(session, settings=publishing, provider=x, commit=False)
    assert outcome.published is True, outcome.reason
    assert x.posted == [approved_draft.body]
    assert outcome.url and outcome.external_id

    row = await session.scalar(
        select(PublishedPost).where(PublishedPost.draft_id == approved_draft.id)
    )
    assert row is not None
    assert approved_draft.status == str(DraftStatus.PUBLISHED)


async def test_the_same_draft_is_never_published_twice(
    session, publishing, approved_draft
) -> None:
    x = FakeX()
    await publish_next(session, settings=publishing, provider=x, commit=False)

    publishing.x_min_minutes_between_posts = 0
    second = await publish_next(
        session, settings=publishing, provider=x, draft_id=approved_draft.id, commit=False
    )
    assert second.published is False
    assert "already been published" in second.reason
    assert len(x.posted) == 1


async def test_a_pending_draft_needs_a_human_at_this_autonomy_level(
    session, publishing, approved_draft
) -> None:
    approved_draft.status = str(DraftStatus.PENDING)
    await session.flush()

    x = FakeX()
    outcome = await publish_next(
        session, settings=publishing, provider=x, draft_id=approved_draft.id, commit=False
    )
    assert outcome.published is False
    assert "human approval" in outcome.reason
    assert x.posted == []


async def test_the_rhythm_is_enforced(session, publishing, approved_draft) -> None:
    """A system that posts every time a cycle finishes spends a 500-post month
    in under a week."""
    session.add(
        PublishedPost(
            draft_id=approved_draft.id,
            platform="x",
            external_id="earlier",
            published_at=datetime.now(UTC) - timedelta(minutes=5),
            is_demo=False,
        )
    )
    await session.flush()

    x = FakeX()
    outcome = await publish_next(session, settings=publishing, provider=x, commit=False)
    assert outcome.published is False
    assert "to go before the next one" in outcome.reason
    assert x.posted == []


async def test_the_text_is_checked_again_at_publish_time(
    session, publishing, approved_draft
) -> None:
    """Approval happened earlier and the text can be edited after it. The last
    word belongs to the check, not to the approval."""
    approved_draft.body = "i tested 9999 tokens and found a clear signal."
    await session.flush()

    x = FakeX()
    outcome = await publish_next(session, settings=publishing, provider=x, commit=False)
    assert outcome.published is False
    assert "failed its own checks" in outcome.reason
    assert x.posted == []


async def test_nothing_is_published_when_there_is_nothing_approved(
    session, publishing
) -> None:
    x = FakeX()
    outcome = await publish_next(session, settings=publishing, provider=x, commit=False)
    assert outcome.published is False
    assert "no approved draft" in outcome.reason


async def test_a_refusal_is_recorded_as_a_skipped_run(
    session, settings, approved_draft
) -> None:
    settings.x_mode = "draft"
    await publish_next(session, settings=settings, provider=FakeX(), commit=False)
    run = await session.scalar(
        select(AgentRun).where(AgentRun.agent_name == PUBLISH_RUN_NAME)
    )
    assert run.status == "SKIPPED"
    assert run.error


async def test_a_provider_failure_does_not_mark_the_draft_published(
    session, publishing, approved_draft
) -> None:
    x = FakeX(raises=PublishingDisabled("app has no write permission"))
    outcome = await publish_next(session, settings=publishing, provider=x, commit=False)

    assert outcome.published is False
    assert approved_draft.status == str(DraftStatus.APPROVED), "unchanged"
    assert (
        await session.scalar(
            select(PublishedPost).where(PublishedPost.draft_id == approved_draft.id)
        )
    ) is None


# -- the endpoint ---------------------------------------------------------


async def test_the_publish_endpoint_still_refuses_in_draft_mode(client, admin_headers):
    drafts = (await client.get("/api/x/drafts")).json()["items"]
    response = await client.post(
        f"/api/x/drafts/{drafts[0]['id']}/publish", headers=admin_headers
    )
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert detail["x_mode"] == "draft"
    assert "implemented" in detail["note"], "say the code exists, not that it is missing"


async def test_the_publish_endpoint_requires_the_operator_token(client):
    drafts = (await client.get("/api/x/drafts")).json()["items"]
    response = await client.post(f"/api/x/drafts/{drafts[0]['id']}/publish")
    assert response.status_code in (401, 403)
