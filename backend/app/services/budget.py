"""The spend guard.

Cost control is an architectural constraint here, not an afterthought: the whole
pipeline exists so that a model is called on what already survived a
deterministic filter. This module is the last gate before a call is paid for.

Two rules, both refusals rather than warnings:

1. **Nothing unmeasurable is spent.** If per-token prices are not configured the
   guard refuses. A call whose cost cannot be computed cannot be counted against
   a budget, and an uncounted call is an unbounded one.
2. **The day's budget is a ceiling, not a target.** Spend is summed from
   `agent_runs` — the same rows the metrics endpoint publishes — so the number
   the guard enforces is the number a reader can audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import AgentRun


class BudgetExceeded(RuntimeError):
    """Raised instead of making a call that would go over the day's budget."""


@dataclass(frozen=True)
class BudgetStatus:
    daily_budget_usd: float
    spent_today_usd: float
    remaining_usd: float
    unpriced_runs_today: int
    """Runs whose cost could not be computed. Any of these makes spend a floor."""
    priced: bool
    """False when the price settings are missing; then no call may be made."""

    @property
    def exhausted(self) -> bool:
        return self.remaining_usd <= 0.0

    def as_dict(self) -> dict:
        return {
            "daily_budget_usd": self.daily_budget_usd,
            "spent_today_usd": round(self.spent_today_usd, 6),
            "remaining_usd": round(self.remaining_usd, 6),
            "unpriced_runs_today": self.unpriced_runs_today,
            "priced": self.priced,
        }


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_budget_status(
    session: AsyncSession, *, settings: Settings | None = None, now: datetime | None = None
) -> BudgetStatus:
    settings = settings or get_settings()
    since = day_start(now)

    spent = float(
        await session.scalar(
            select(func.coalesce(func.sum(AgentRun.estimated_cost_usd), 0.0)).where(
                AgentRun.started_at >= since
            )
        )
        or 0.0
    )
    unpriced = int(
        await session.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.started_at >= since)
            .where(AgentRun.model.is_not(None))
            .where(AgentRun.estimated_cost_usd.is_(None))
        )
        or 0
    )
    priced = (
        settings.model_price_input_usd_per_mtok is not None
        and settings.model_price_output_usd_per_mtok is not None
    )

    return BudgetStatus(
        daily_budget_usd=settings.llm_daily_budget_usd,
        spent_today_usd=spent,
        remaining_usd=max(0.0, settings.llm_daily_budget_usd - spent),
        unpriced_runs_today=unpriced,
        priced=priced,
    )


async def require_budget(
    session: AsyncSession, *, settings: Settings | None = None, now: datetime | None = None
) -> BudgetStatus:
    """Raise unless there is measurable budget left for one more call."""
    status = await get_budget_status(session, settings=settings, now=now)

    if not status.priced:
        raise BudgetExceeded(
            "MODEL_PRICE_INPUT_USD_PER_MTOK and MODEL_PRICE_OUTPUT_USD_PER_MTOK are "
            "not set. A call whose cost cannot be measured cannot be counted against "
            "a budget, so no model call is made."
        )
    if status.exhausted:
        raise BudgetExceeded(
            f"today's model budget is spent: ${status.spent_today_usd:.4f} of "
            f"${status.daily_budget_usd:.2f}. The deterministic engines keep running."
        )
    if status.unpriced_runs_today:
        raise BudgetExceeded(
            f"{status.unpriced_runs_today} model runs today recorded no cost, so "
            f"${status.spent_today_usd:.4f} is a floor and not the day's spend. "
            "Refusing to spend against a number that is known to be incomplete."
        )
    return status


def next_reset(now: datetime | None = None) -> datetime:
    return day_start(now) + timedelta(days=1)
