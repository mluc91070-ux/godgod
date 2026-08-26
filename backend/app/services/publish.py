"""Publishing a draft to X.

The system has a voice, and this is where it uses it in public. Four gates
stand between a result and a post, and each one exists because of a specific
way this goes wrong:

1. **The deployment must be configured to publish.** `X_MODE` is the switch,
   and no argument to any function here overrides it.
2. **The draft must have passed the reviewer.** Deterministic checks first, so
   a post can never contain a number absent from the result it describes.
3. **A human must have approved it**, unless the operator has explicitly moved
   the autonomy level up. That is a decision, not a default.
4. **A minimum interval between posts.** A research system that posts every
   time a cycle finishes is a bot, and it spends a 500-post month in a week.

Nothing is ever published twice: a draft with a `published_posts` row is done,
and that check is a query rather than a flag anyone can forget to set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.guards import check_draft
from app.agents.reviewer import source_facts
from app.core.config import Settings, get_settings
from app.core.enums import DraftStatus, EventType
from app.models import AgentRun, ContentDraft, PublishedPost, SystemEvent
from app.models.base import as_utc, utcnow
from app.providers.base import ProviderNotConfigured
from app.providers.x import PublishingDisabled, XCallFailed, XRateLimited, get_x_provider

PUBLISH_RUN_NAME = "x-publisher"

AUTONOMY_AUTOPUBLISH = 3
"""Below this, a human approval is required before anything goes out."""


@dataclass
class PublishOutcome:
    published: bool
    draft_id: str | None = None
    external_id: str | None = None
    url: str | None = None
    reason: str | None = None
    """Why nothing was published. Always set when `published` is false."""

    def as_dict(self) -> dict[str, Any]:
        return {
            "published": self.published,
            "draft_id": self.draft_id,
            "external_id": self.external_id,
            "url": self.url,
            "reason": self.reason,
        }


async def last_published_at(session: AsyncSession) -> datetime | None:
    return as_utc(await session.scalar(select(func.max(PublishedPost.published_at))))


async def already_published(session: AsyncSession, draft_id: str) -> bool:
    return bool(
        await session.scalar(
            select(PublishedPost.id).where(PublishedPost.draft_id == draft_id)
        )
    )


async def next_publishable_draft(
    session: AsyncSession, *, settings: Settings
) -> ContentDraft | None:
    """The oldest approved draft that has not gone out.

    Oldest first, deliberately: publishing the newest would let a busy hour bury
    a result that was already worth saying.
    """
    required = (
        DraftStatus.APPROVED
        if settings.autonomy_level < AUTONOMY_AUTOPUBLISH
        else DraftStatus.PENDING
    )
    candidates = (
        await session.scalars(
            select(ContentDraft)
            .where(ContentDraft.status.in_([str(DraftStatus.APPROVED), str(required)]))
            .order_by(ContentDraft.created_at)
        )
    ).all()
    for draft in candidates:
        if not await already_published(session, draft.id):
            return draft
    return None


async def _record(
    session: AsyncSession,
    *,
    outcome: PublishOutcome,
    started: datetime,
    level: str,
    message: str,
) -> None:
    session.add(
        SystemEvent(
            seq=int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1,
            event_type=str(EventType.ERROR if level == "ERROR" else EventType.DRAFT_REVIEWED),
            message=message,
            level=level,
            ref_type="content_draft",
            ref_id=outcome.draft_id,
            occurred_at=utcnow(),
            is_demo=False,
        )
    )
    session.add(
        AgentRun(
            agent_name=PUBLISH_RUN_NAME,
            model=None,
            input_summary=f"draft {outcome.draft_id}" if outcome.draft_id else "no draft",
            output_summary=message[:2000],
            duration_ms=int((utcnow() - started).total_seconds() * 1000),
            status="OK" if outcome.published else "SKIPPED",
            error=None if outcome.published else outcome.reason,
            estimated_cost_usd=0.0,
            started_at=started,
            is_demo=False,
        )
    )
    await session.flush()


async def publish_next(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    provider: Any = None,
    draft_id: str | None = None,
    commit: bool = True,
) -> PublishOutcome:
    """Publish one draft, or explain why nothing went out."""
    settings = settings or get_settings()
    started = utcnow()

    def refuse(reason: str, *, draft: ContentDraft | None = None) -> PublishOutcome:
        return PublishOutcome(
            published=False, reason=reason, draft_id=draft.id if draft else None
        )

    if settings.x_mode != "publish":
        outcome = refuse(
            f"X_MODE={settings.x_mode}; the deployment is not configured to publish."
        )
        await _record(session, outcome=outcome, started=started, level="INFO",
                      message=f"nothing published: {outcome.reason}")
        if commit:
            await session.commit()
        return outcome

    # -- rhythm -----------------------------------------------------------
    last = await last_published_at(session)
    if last is not None:
        wait = timedelta(minutes=settings.x_min_minutes_between_posts)
        elapsed = datetime.now(UTC) - last
        if elapsed < wait:
            remaining = int((wait - elapsed).total_seconds() // 60)
            outcome = refuse(
                f"last post was {int(elapsed.total_seconds() // 60)} minutes ago; "
                f"{remaining} to go before the next one."
            )
            await _record(session, outcome=outcome, started=started, level="INFO",
                          message=f"nothing published: {outcome.reason}")
            if commit:
                await session.commit()
            return outcome

    # -- what to say ------------------------------------------------------
    if draft_id:
        draft = await session.scalar(select(ContentDraft).where(ContentDraft.id == draft_id))
        if draft is None:
            return refuse("draft not found")
        if await already_published(session, draft.id):
            return refuse("that draft has already been published", draft=draft)
    else:
        draft = await next_publishable_draft(session, settings=settings)

    if draft is None:
        outcome = refuse("no approved draft is waiting.")
        await _record(session, outcome=outcome, started=started, level="INFO",
                      message=f"nothing published: {outcome.reason}")
        if commit:
            await session.commit()
        return outcome

    if settings.autonomy_level < AUTONOMY_AUTOPUBLISH and draft.status != str(
        DraftStatus.APPROVED
    ):
        return refuse(
            f"draft is {draft.status} and autonomy level {settings.autonomy_level} "
            "requires a human approval before publishing.",
            draft=draft,
        )

    # -- the last check, on the text that is about to go out --------------
    facts = await source_facts(session, draft)
    check = check_draft(draft.body, facts, outcome=str(facts.get("outcome") or "") or None)
    if not check.ok:
        outcome = refuse(
            "the text failed its own checks at publish time: "
            + "; ".join(check.reasons),
            draft=draft,
        )
        await _record(session, outcome=outcome, started=started, level="WARN",
                      message=f"nothing published: {outcome.reason}")
        if commit:
            await session.commit()
        return outcome

    provider = provider or get_x_provider(settings)
    try:
        result = await provider.create_post(draft.body)
    except (PublishingDisabled, ProviderNotConfigured, XRateLimited, XCallFailed) as exc:
        outcome = refuse(f"{type(exc).__name__}: {exc}", draft=draft)
        await _record(session, outcome=outcome, started=started, level="ERROR",
                      message=f"publish failed: {outcome.reason}")
        if commit:
            await session.commit()
        return outcome

    external_id = result.get("id")
    url = f"https://x.com/i/web/status/{external_id}" if external_id else None
    published_at = datetime.now(UTC)

    session.add(
        PublishedPost(
            draft_id=draft.id,
            platform="x",
            external_id=external_id,
            url=url,
            published_at=published_at,
            is_demo=False,
        )
    )
    draft.status = str(DraftStatus.PUBLISHED)
    await session.flush()

    outcome = PublishOutcome(
        published=True, draft_id=draft.id, external_id=external_id, url=url
    )
    await _record(
        session,
        outcome=outcome,
        started=started,
        level="INFO",
        message=f"published to x: {url or external_id}",
    )
    if commit:
        await session.commit()
    return outcome
