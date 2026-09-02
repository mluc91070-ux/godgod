"""Sampling what people are looking up, once per cycle.

One reading of a ranking, stored as rows. That is the whole job, and almost all
of the code is about the three ways it could quietly stop being a measurement:

- **A missing token is not a zero.** Only entries that appear in the ranking
  get a row. "Not ranked" and "ranked last" are different facts and the table
  can only hold the first, which is the honest one.
- **A link needs an address.** `token_id` is set on an exact contract-address
  match and on nothing else. Symbols collide by the dozen across chains, and a
  wrong link puts someone else's attention on a real token's record — the same
  rule the social collector had, kept after it went.
- **A short run is not a quiet market.** Resolutions cost a request each and
  the keyless tier is rate-limited, so a run that hits its budget records how
  many names it left unresolved instead of reporting a shorter list.

Addresses are looked up once. The mapping from a feed's id to a contract does
not change, so the previous rows are read back rather than the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import EventType
from app.models import AgentRun, AttentionSnapshot, SystemEvent, Token
from app.models.base import as_utc, utcnow
from app.providers.attention import (
    AttentionCallFailed,
    AttentionProvider,
    get_attention_provider,
)
from app.providers.base import ProviderNotConfigured

ATTENTION_RUN_NAME = "attention-collector"
ATTENTION_SOURCE = "search-ranking-v1"
"""The feed and how the number is read. A ranking computed differently is a
different measurement, and a bump here keeps the two from being compared."""


@dataclass
class AttentionReport:
    ranked: int = 0
    """Entries the feed returned this run."""
    stored: int = 0
    linked: int = 0
    """Of those, the ones an address tied to a token this system measures."""
    resolved: int = 0
    """Addresses looked up over the network this run."""
    unresolved: int = 0
    """Names the call budget did not reach. The difference between "not on a
    chain we read" and "we stopped asking"."""
    dropped: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "ranked": self.ranked,
            "stored": self.stored,
            "linked": self.linked,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "dropped": self.dropped,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "complete": self.error is None,
            "llm_calls": 0,
        }


async def _known_address(session: AsyncSession, ref: str) -> tuple[str, str] | None:
    """A chain and address this feed already gave us for that name.

    Read back rather than looked up again: the mapping does not change, and a
    request per coin per run would spend the whole rate limit on answers that
    were already known.
    """
    row = await session.scalar(
        select(AttentionSnapshot)
        .where(
            AttentionSnapshot.ref == ref,
            AttentionSnapshot.address.is_not(None),
        )
        .order_by(AttentionSnapshot.observed_at.desc())
        .limit(1)
    )
    if row is None or row.address is None:
        return None
    return (row.chain or "", row.address)


async def _next_event_seq(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1


async def collect_attention(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    provider: AttentionProvider | None = None,
    as_of: datetime | None = None,
    commit: bool = True,
) -> AttentionReport:
    """Read the ranking once and store what it said."""
    settings = settings or get_settings()
    provider = provider or get_attention_provider(settings)
    started = utcnow()
    now = datetime.now(UTC)
    slot = settings.snapshot_slot_minutes
    observed_at = as_utc(as_of) or now.replace(
        minute=(now.minute // slot) * slot, second=0, microsecond=0
    )
    report = AttentionReport()

    try:
        ranking = await provider.trending()
    except (ProviderNotConfigured, AttentionCallFailed) as exc:
        report.error = f"{type(exc).__name__}: {exc}"
        report.duration_ms = int((utcnow() - started).total_seconds() * 1000)
        return report

    report.ranked = len(ranking)

    already = await session.scalar(
        select(func.count())
        .select_from(AttentionSnapshot)
        .where(AttentionSnapshot.observed_at == observed_at)
    )
    if already:
        # One reading per slot, like the chain collector. A second pass in the
        # same slot is a duplicate, not a second measurement.
        report.drop("already_sampled_this_slot")
        report.duration_ms = int((utcnow() - started).total_seconds() * 1000)
        return report

    for entry in ranking:
        chain: str | None = None
        address: str | None = None

        known = await _known_address(session, entry.ref)
        if known is not None:
            chain, address = known[0] or None, known[1]
        elif report.resolved >= settings.attention_max_resolutions:
            report.unresolved += 1
            report.drop("address_not_resolved_this_run")
        else:
            try:
                platforms = await provider.platforms(entry.ref)
                report.resolved += 1
            except (ProviderNotConfigured, AttentionCallFailed) as exc:
                # The ranking still stands; this entry simply has no address
                # yet, and it will be resolved on a later run.
                report.unresolved += 1
                report.error = f"{type(exc).__name__}: {exc}"
                platforms = {}
            wanted = [name for name in settings.market_chains if name in platforms]
            if wanted:
                chain = wanted[0]
                address = platforms[chain]
            elif platforms:
                # It lives somewhere this system does not measure. A real
                # answer, and a different one from "the feed did not say".
                report.drop("not_on_a_measured_chain")
            else:
                report.drop("no_address_reported")

        token_id: str | None = None
        if address:
            # Exact address match, never a symbol. Two chains hold a dozen of
            # most symbols, and a wrong link puts someone else's attention on a
            # real token's record.
            token = await session.scalar(
                select(Token).where(
                    func.lower(Token.address) == address.lower(),
                    Token.chain == chain,
                )
            )
            if token is not None:
                token_id = token.id
                report.linked += 1

        session.add(
            AttentionSnapshot(
                observed_at=observed_at,
                source=ATTENTION_SOURCE,
                ref=entry.ref,
                symbol=entry.symbol,
                name=entry.name,
                rank=entry.rank,
                market_cap_rank=entry.market_cap_rank,
                chain=chain,
                address=address,
                token_id=token_id,
                is_demo=False,
            )
        )
        report.stored += 1

    await session.flush()
    report.duration_ms = int((utcnow() - started).total_seconds() * 1000)

    message = (
        f"attention: {report.stored} ranked entries stored, {report.linked} tied to a "
        f"measured token"
    )
    if report.unresolved:
        message += f", {report.unresolved} names left unresolved"
    if report.error:
        message += f" — {report.error}"

    session.add(
        SystemEvent(
            seq=await _next_event_seq(session),
            event_type=str(EventType.ERROR if report.error else EventType.OBSERVATION),
            message=message,
            level="WARN" if report.error else "INFO",
            ref_type="attention-collector",
            occurred_at=datetime.now(UTC),
            is_demo=False,
        )
    )
    session.add(
        AgentRun(
            agent_name=ATTENTION_RUN_NAME,
            model=None,
            input_summary="search ranking, one page",
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
