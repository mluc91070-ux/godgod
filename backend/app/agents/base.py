"""Running one agent.

Every model call goes through `run_agent`, which is where the four things that
must never be optional happen: the budget is checked before the call, the run is
recorded whether it succeeded or failed, the cost is stored as measured or as
`None`, and a failure is written to the event log rather than swallowed.

An agent that returns nothing because the provider errored must never look like
an agent that found nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import EventType
from app.models import Agent, AgentRun, SystemEvent
from app.models.base import utcnow
from app.providers.base import ProviderNotConfigured
from app.providers.model import ModelCallFailed, ModelProvider, ModelResponse, get_model_provider
from app.services.budget import BudgetExceeded, require_budget

IMPLEMENTED_AGENTS = ("writer", "reviewer")
"""Agents with a model behind them today.

The other four roles in the roster — observer, researcher, data_scientist,
critic — are implemented as deterministic engines instead. Their `implemented`
flag stays false because the *agent* does not exist, and saying otherwise on
/api/agents would be a claim about a capability nobody built.
"""


@dataclass
class AgentOutcome:
    ok: bool
    text: str | None
    response: ModelResponse | None
    error: str | None
    run_id: str | None
    cost_usd: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "run_id": self.run_id,
            "cost_usd": self.cost_usd,
            "model": self.response.model if self.response else None,
            "input_tokens": self.response.input_tokens if self.response else None,
            "output_tokens": self.response.output_tokens if self.response else None,
        }


async def _next_event_seq(session: AsyncSession) -> int:
    from sqlalchemy import func

    return int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1


async def _log(
    session: AsyncSession, *, message: str, level: str, ref_id: str | None, is_demo: bool
) -> None:
    session.add(
        SystemEvent(
            seq=await _next_event_seq(session),
            event_type=str(EventType.ERROR if level == "ERROR" else EventType.AGENT_RUN),
            message=message,
            level=level,
            ref_type="agent_run",
            ref_id=ref_id,
            occurred_at=utcnow(),
            is_demo=is_demo,
        )
    )
    await session.flush()


async def run_agent(
    session: AsyncSession,
    *,
    name: str,
    role: str,
    system: str,
    prompt: str,
    input_summary: str,
    max_tokens: int = 4096,
    effort: str | None = "low",
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    is_demo: bool = True,
) -> AgentOutcome:
    """Call the model for one agent and record the attempt either way."""
    settings = settings or get_settings()
    provider = provider or get_model_provider(settings)
    started = utcnow()

    agent_row = await session.scalar(select(Agent).where(Agent.name == name))

    async def record(
        *,
        status: str,
        response: ModelResponse | None,
        error: str | None,
        output_summary: str | None,
    ) -> str:
        run = AgentRun(
            agent_id=agent_row.id if agent_row else None,
            agent_name=name,
            model=response.model if response else None,
            input_summary=input_summary[:2000],
            output_summary=(output_summary or "")[:2000] or None,
            duration_ms=int((utcnow() - started).total_seconds() * 1000),
            status=status,
            error=error,
            input_tokens=response.input_tokens if response else None,
            output_tokens=response.output_tokens if response else None,
            estimated_cost_usd=response.cost_usd if response else None,
            started_at=started,
            is_demo=is_demo,
        )
        session.add(run)
        await session.flush()
        return run.id

    # -- the gate before the spend ----------------------------------------
    try:
        await require_budget(session, settings=settings)
    except BudgetExceeded as exc:
        run_id = await record(
            status="SKIPPED", response=None, error=str(exc), output_summary=None
        )
        await _log(
            session,
            message=f"{name}: no call made — {exc}",
            level="WARN",
            ref_id=run_id,
            is_demo=is_demo,
        )
        return AgentOutcome(
            ok=False, text=None, response=None, error=str(exc), run_id=run_id, cost_usd=None
        )

    # -- the call ----------------------------------------------------------
    try:
        response = await provider.complete(
            system=system,
            prompt=prompt,
            role=role,
            max_tokens=max_tokens,
            effort=effort,
        )
    except (ProviderNotConfigured, ModelCallFailed, ValueError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        run_id = await record(status="ERROR", response=None, error=error, output_summary=None)
        await _log(
            session,
            message=f"{name} failed: {error}",
            level="ERROR",
            ref_id=run_id,
            is_demo=is_demo,
        )
        return AgentOutcome(
            ok=False, text=None, response=None, error=error, run_id=run_id, cost_usd=None
        )

    if response.truncated:
        # A truncated answer is a partial answer; treating it as complete is how
        # half a sentence becomes a published claim.
        error = "the model stopped at max_tokens; the answer is incomplete"
        run_id = await record(
            status="ERROR", response=response, error=error, output_summary=response.text[:400]
        )
        await _log(
            session, message=f"{name}: {error}", level="ERROR", ref_id=run_id, is_demo=is_demo
        )
        return AgentOutcome(
            ok=False,
            text=None,
            response=response,
            error=error,
            run_id=run_id,
            cost_usd=response.cost_usd,
        )

    run_id = await record(
        status="OK", response=response, error=None, output_summary=response.text[:400]
    )
    return AgentOutcome(
        ok=True,
        text=response.text,
        response=response,
        error=None,
        run_id=run_id,
        cost_usd=response.cost_usd,
    )
