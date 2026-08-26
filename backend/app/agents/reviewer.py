"""The reviewer.

The last gate before anything could become public. It answers one question:
does this draft claim more than the row it came from?

Two verdicts are combined, and the strict one wins:

1. **Deterministic checks** — voice, length, links, advice, certainty about an
   inconclusive result, and every number grounded in the source row. These run
   whether or not a model is configured, and a failure here is final: no model
   opinion can approve a draft that states an ungrounded number.
2. **The model's reading** — the judgement a regex cannot make: does the
   sentence imply a finding the result does not support?

With no model configured the deterministic verdict stands alone and the notes
say so, because a review that did not happen must not read like one that did.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import run_agent
from app.agents.guards import check_draft
from app.agents.writer import facts_for
from app.core.config import Settings, get_settings
from app.core.enums import EventType
from app.models import ContentDraft, Experiment, ExperimentResult, SystemEvent
from app.models.base import utcnow
from app.providers.model import ModelProvider

REVIEWER_VERSION = "reviewer-v1"

SYSTEM = """You are the reviewer for GODGOD, an autonomous research system. You
are the last gate before a post could become public, and your only question is
whether the draft claims more than the recorded result supports.

Reject if the draft:
- states or implies a finding the outcome does not support (an inconclusive
  result is not a discovery, a rejection is not a warning about the future)
- contains a number that is not in the facts
- gives advice, predicts a price, or reads as promotion
- describes a real asset as if the system had traded or held it

Approve if it is an accurate, plain description of the recorded result,
including when the result is a failure.

Answer with JSON only: {"verdict": "APPROVE" | "REJECT", "reason": "<one short
sentence, lowercase>"}"""


@dataclass
class ReviewOutcome:
    verdict: str
    """APPROVE or REJECT."""
    reasons: list[str] = field(default_factory=list)
    model_verdict: str | None = None
    """None when no model reviewed it. Not the same as an approval."""
    model_reason: str | None = None
    run_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None

    @property
    def approved(self) -> bool:
        return self.verdict == "APPROVE"

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reasons": self.reasons,
            "model_verdict": self.model_verdict,
            "model_reason": self.model_reason,
            "run_id": self.run_id,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "version": REVIEWER_VERSION,
        }


def parse_verdict(text: str) -> tuple[str | None, str | None]:
    """Read the model's JSON answer without trusting its shape."""
    body = text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        return None, None
    try:
        parsed = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None, None
    verdict = str(parsed.get("verdict", "")).upper()
    if verdict not in {"APPROVE", "REJECT"}:
        return None, None
    reason = parsed.get("reason")
    return verdict, str(reason) if reason else None


async def source_facts(session: AsyncSession, draft: ContentDraft) -> dict[str, Any]:
    """The row the draft claims to describe, or an empty set of facts.

    An empty set is deliberately strict: with nothing to check against, every
    number in the draft is ungrounded and the draft is rejected.
    """
    if draft.source_kind == "experiment_result" and draft.source_id:
        result = await session.scalar(
            select(ExperimentResult).where(ExperimentResult.id == draft.source_id)
        )
        if result is None:
            return {}
        experiment = await session.scalar(
            select(Experiment)
            .options(selectinload(Experiment.hypothesis))
            .where(Experiment.id == result.experiment_id)
        )
        return facts_for(experiment, result) if experiment else {}

    if draft.source_kind == "experiment" and draft.source_id:
        experiment = await session.scalar(
            select(Experiment)
            .options(selectinload(Experiment.hypothesis), selectinload(Experiment.results))
            .where(Experiment.id == draft.source_id)
        )
        if experiment is None or not experiment.results:
            return {}
        return facts_for(experiment, experiment.results[0])

    return {}


def _outcome_of(facts: dict[str, Any]) -> str | None:
    value = facts.get("outcome")
    return str(value) if value else None


async def review_draft(
    session: AsyncSession,
    draft_id: str,
    *,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    commit: bool = True,
) -> ReviewOutcome:
    settings = settings or get_settings()

    draft = await session.scalar(select(ContentDraft).where(ContentDraft.id == draft_id))
    if draft is None:
        return ReviewOutcome(verdict="REJECT", reasons=["draft not found"])

    facts = await source_facts(session, draft)
    if not facts:
        outcome = ReviewOutcome(
            verdict="REJECT",
            reasons=[
                "the draft does not point at a result that can be checked; "
                "a draft with no verifiable source cannot be approved"
            ],
        )
        await _store(session, draft, outcome, commit=commit)
        return outcome

    check = check_draft(draft.body, facts, outcome=_outcome_of(facts))
    reasons = list(check.reasons)

    model_verdict: str | None = None
    model_reason: str | None = None
    run_id: str | None = None
    cost: float | None = None
    error: str | None = None

    if check.ok:
        # Only worth paying for a reading when the mechanical checks passed.
        prompt = (
            "facts:\n"
            + "\n".join(f"- {key}: {value}" for key, value in facts.items())
            + f"\n\ndraft:\n{draft.body}\n\nanswer with the json object."
        )
        agent = await run_agent(
            session,
            name="reviewer",
            role="MODEL_CRITIC",
            system=SYSTEM,
            prompt=prompt,
            input_summary=f"draft {draft.id} against result {draft.source_id}",
            max_tokens=200,
                settings=settings,
            provider=provider,
            is_demo=bool(draft.is_demo),
        )
        run_id, cost, error = agent.run_id, agent.cost_usd, agent.error

        if agent.ok and agent.text:
            model_verdict, model_reason = parse_verdict(agent.text)
            if model_verdict is None:
                reasons.append("the reviewer model did not return a usable verdict")
            elif model_verdict == "REJECT":
                reasons.append(f"reviewer: {model_reason or 'rejected without a reason'}")

    verdict = "APPROVE" if not reasons else "REJECT"
    outcome = ReviewOutcome(
        verdict=verdict,
        reasons=reasons,
        model_verdict=model_verdict,
        model_reason=model_reason,
        run_id=run_id,
        cost_usd=cost,
        error=error,
    )
    await _store(session, draft, outcome, commit=commit)
    return outcome


async def _store(
    session: AsyncSession, draft: ContentDraft, outcome: ReviewOutcome, *, commit: bool
) -> None:
    """Record the verdict on the draft. Approval is a verdict, never a publish."""
    note = "; ".join(outcome.reasons) if outcome.reasons else "no objection recorded."
    if outcome.model_verdict is None:
        note = (
            f"{note} checked deterministically only ({REVIEWER_VERSION}); "
            "no model reviewed this draft."
        )
    draft.reviewer_verdict = outcome.verdict
    draft.reviewer_notes = note[:4000]
    if outcome.verdict == "REJECT":
        draft.status = "REJECTED"
        draft.rejection_reason = note[:4000]

    session.add(
        SystemEvent(
            seq=int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1,
            event_type=str(EventType.DRAFT_REVIEWED),
            message=f"draft {outcome.verdict.lower()}ed by the reviewer",
            level="INFO" if outcome.approved else "WARN",
            ref_type="content_draft",
            ref_id=draft.id,
            occurred_at=utcnow(),
            is_demo=bool(draft.is_demo),
        )
    )
    await session.flush()
    if commit:
        await session.commit()
