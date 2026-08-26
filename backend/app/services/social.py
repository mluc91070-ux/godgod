"""Collecting posts from X into the research database.

The same discipline as the observation pipeline: every post that is not stored
is counted under a named reason, so "collected nothing" is distinguishable from
"looked at nothing" — and from "the quota was gone", which is the failure mode
that matters most here because it is invisible otherwise.

Nothing in this module reasons about what a post *means*. It stores rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import EventType
from app.models import AgentRun, SocialAccount, SocialPost, SystemEvent, Token
from app.models.base import utcnow
from app.providers.base import ProviderNotConfigured
from app.providers.x import HttpXProvider, XCallFailed, XSearchResult, get_x_provider

COLLECTOR_RUN_NAME = "x-collector"


@dataclass
class CollectionReport:
    queries: int = 0
    fetched: int = 0
    stored: int = 0
    accounts_created: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    """Why a fetched post was not stored. Never silent."""
    rate_limited: bool = False
    """True if any query hit the quota. Then `fetched` is a floor, not a total."""
    reset_at: datetime | None = None
    error: str | None = None
    duration_ms: int = 0

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "fetched": self.fetched,
            "stored": self.stored,
            "accounts_created": self.accounts_created,
            "dropped": self.dropped,
            "rate_limited": self.rate_limited,
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "complete": not self.rate_limited and self.error is None,
            "llm_calls": 0,
        }


def match_terms(text: str, terms: list[str]) -> list[str]:
    lowered = text.lower()
    return [term for term in terms if term.lower() in lowered]


async def _token_address_in(session: AsyncSession, text: str) -> str | None:
    """Link a post to a token only on an exact address match.

    Symbol matching is deliberately not done: `$MOON` in a post is not evidence
    that it refers to the row called MOON, and a wrong link would put fabricated
    social activity on a real token's record.
    """
    if not text:
        return None
    addresses = (await session.scalars(select(Token.address))).all()
    for address in addresses:
        if address and address in text:
            return address
    return None


async def _get_or_create_account(
    session: AsyncSession, *, author_id: str | None, handle: str | None, report: CollectionReport
) -> SocialAccount | None:
    if not author_id:
        return None
    account = await session.scalar(
        select(SocialAccount).where(
            SocialAccount.platform == "x", SocialAccount.external_id == author_id
        )
    )
    if account is not None:
        if handle and account.handle != handle:
            account.handle = handle
        return account

    account = SocialAccount(
        platform="x", external_id=author_id, handle=handle, is_demo=False
    )
    session.add(account)
    await session.flush()
    report.accounts_created += 1
    return account


async def _next_event_seq(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1


async def collect_posts(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    provider: Any = None,
    queries: list[str] | None = None,
    commit: bool = True,
) -> CollectionReport:
    """Run each configured search once and store what comes back.

    Live data, so every row written here carries `is_demo=False` — it is never
    mixed with the fixture rows, which is the whole point of the flag.
    """
    settings = settings or get_settings()
    provider = provider or get_x_provider(settings)
    started = utcnow()
    report = CollectionReport()

    if not isinstance(provider, HttpXProvider) and not hasattr(provider, "search"):
        report.error = (
            "X_BEARER_TOKEN is not configured; no search was performed. "
            "The system collected nothing, and says so rather than reporting zero posts."
        )
        report.duration_ms = int((utcnow() - started).total_seconds() * 1000)
        return report

    terms = queries or settings.x_search_terms
    remaining = settings.x_max_posts_per_run

    for query in terms:
        if remaining <= 0:
            report.drop("run_budget_reached")
            break
        report.queries += 1

        try:
            result: XSearchResult = await provider.search(query, limit=min(remaining, 100))
        except (ProviderNotConfigured, XCallFailed) as exc:
            report.error = f"{type(exc).__name__}: {exc}"
            break

        if result.rate_limited:
            report.rate_limited = True
            report.reset_at = result.reset_at
            break

        for post in result.posts:
            report.fetched += 1
            remaining -= 1

            if settings.x_exclude_reposts and post.is_repost:
                report.drop("repost")
                continue
            if (post.likes or 0) < settings.x_min_likes:
                report.drop("below_min_likes")
                continue
            if not post.text.strip():
                report.drop("empty_text")
                continue

            existing = await session.scalar(
                select(SocialPost).where(
                    SocialPost.platform == "x", SocialPost.external_id == post.external_id
                )
            )
            if existing is not None:
                report.drop("already_stored")
                continue

            account = await _get_or_create_account(
                session, author_id=post.author_id, handle=post.author_handle, report=report
            )
            session.add(
                SocialPost(
                    platform="x",
                    external_id=post.external_id,
                    account_id=account.id if account else None,
                    posted_at=post.posted_at,
                    text=post.text,
                    lang=post.lang,
                    likes=post.likes,
                    reposts=post.reposts,
                    replies=post.replies,
                    matched_terms=match_terms(post.text, terms),
                    mentions_token_address=await _token_address_in(session, post.text),
                    source="x-recent-search",
                    is_demo=False,
                )
            )
            await session.flush()
            report.stored += 1

    report.duration_ms = int((utcnow() - started).total_seconds() * 1000)

    message = (
        f"x collector: {report.stored} stored of {report.fetched} fetched "
        f"across {report.queries} queries"
    )
    if report.rate_limited:
        message += " (stopped by the rate limit; this is a floor, not a total)"
    if report.error:
        message += f" — {report.error}"

    session.add(
        SystemEvent(
            seq=await _next_event_seq(session),
            event_type=str(EventType.ERROR if report.error else EventType.OBSERVATION),
            message=message,
            level="WARN" if (report.error or report.rate_limited) else "INFO",
            ref_type="x-collector",
            occurred_at=datetime.now(UTC),
            is_demo=False,
        )
    )
    session.add(
        AgentRun(
            agent_name=COLLECTOR_RUN_NAME,
            model=None,
            input_summary=f"{len(terms)} queries: {', '.join(terms)[:400]}",
            output_summary=message[:2000],
            duration_ms=report.duration_ms,
            status="ERROR" if report.error else "OK",
            error=report.error,
            estimated_cost_usd=0.0,
            started_at=started,
            is_demo=False,
        )
    )
    await session.flush()

    if commit:
        await session.commit()
    return report
