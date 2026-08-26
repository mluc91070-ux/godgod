"""The writer.

One question: is there something worth communicating, and how does it read in
this system's voice?

The writer is given facts and is not given the database. It cannot look up a
number, so it cannot invent one and have it survive: everything it writes is
checked against the exact row it was asked to describe, and a draft containing a
number that is not in that row is discarded rather than stored.

If no model is configured this module does nothing and says so. The templated
draft written by the deterministic cycle stays as it is — a template that is
honest beats a sentence nobody can check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import run_agent
from app.agents.guards import check_draft
from app.core.config import Settings, get_settings
from app.core.enums import ContentType, EventType
from app.models import ContentDraft, Experiment, ExperimentResult, SystemEvent
from app.models.base import utcnow
from app.providers.model import ModelProvider

WRITER_SOURCE = "writer-v1"
"""Distinguishes a model-written draft from the templated one (`templated-v1`)."""

SYSTEM = """You are GODGOD, an autonomous research system studying how meme
narratives propagate on Solana. You are not a trading bot and you never discuss
what anyone should buy or sell.

Voice: lowercase, short lines, calm, analytical, skeptical, occasionally
philosophical. Never crypto twitter, never a corporate chatbot, never excited.

You are writing one short public post about a result your own experiment
produced. Rules that are not stylistic:

- Use only the numbers given to you below. Never introduce a number that is not
  in the facts, never round one into a different number, and never estimate.
- Report the outcome as it is recorded. An inconclusive result is inconclusive;
  do not soften it into a finding or dramatise it into a failure.
- If the result was rejected, say so plainly. Being wrong is publishable here.
- No links, no hashtags, no emoji, no advice, no prediction.
- 280 characters maximum, lowercase throughout.

Reply with the post text only. No preamble, no quotation marks, no explanation."""


@dataclass
class WriterOutcome:
    ok: bool
    draft_id: str | None = None
    text: str | None = None
    reasons: list[str] = field(default_factory=list)
    """Why the draft was refused, when it was."""
    error: str | None = None
    run_id: str | None = None
    cost_usd: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "draft_id": self.draft_id,
            "text": self.text,
            "reasons": self.reasons,
            "error": self.error,
            "run_id": self.run_id,
            "cost_usd": self.cost_usd,
        }


def facts_for(
    experiment: Experiment, result: ExperimentResult
) -> dict[str, Any]:
    """Exactly what the writer is allowed to know, and to say."""
    hypothesis = experiment.hypothesis
    metrics = result.metrics or {}
    return {
        "hypothesis_number": hypothesis.seq if hypothesis else None,
        "question": hypothesis.question if hypothesis else experiment.title,
        "falsification_condition": hypothesis.falsification_condition if hypothesis else None,
        "outcome": result.outcome,
        "summary": result.summary,
        "sample_size": experiment.sample_size,
        "n_exposed": metrics.get("n_exposed"),
        "n_control": metrics.get("n_control"),
        "rate_exposed": metrics.get("rate_exposed"),
        "rate_control": metrics.get("rate_control"),
        "difference_pp": metrics.get("difference_pp"),
        "distinct_tokens": metrics.get("distinct_tokens"),
        "p_value": result.p_value,
        "effect_size": result.effect_size,
        "critic_verdict": result.critic_verdict,
        "limitations": result.limitations,
    }


def build_prompt(facts: dict[str, Any]) -> str:
    lines = ["facts (these are the only numbers you may use):"]
    for key, value in facts.items():
        if value is None:
            lines.append(f"- {key}: not measured")
        else:
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("write the post.")
    return "\n".join(lines)


def content_type_for(outcome: str) -> ContentType:
    if outcome == "REJECTED":
        return ContentType.FAILURE
    if outcome == "SUPPORTED":
        return ContentType.RESULT
    return ContentType.EXPERIMENT


async def write_draft_for_result(
    session: AsyncSession,
    result_id: str,
    *,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    commit: bool = True,
) -> WriterOutcome:
    """Ask the model for one post about one recorded result."""
    settings = settings or get_settings()

    result = await session.scalar(
        select(ExperimentResult).where(ExperimentResult.id == result_id)
    )
    if result is None:
        return WriterOutcome(ok=False, error="result not found")

    experiment = await session.scalar(
        select(Experiment)
        .options(selectinload(Experiment.hypothesis))
        .where(Experiment.id == result.experiment_id)
    )
    if experiment is None:
        return WriterOutcome(ok=False, error="experiment not found")

    facts = facts_for(experiment, result)
    outcome = await run_agent(
        session,
        name="writer",
        role="MODEL_WRITER",
        system=SYSTEM,
        prompt=build_prompt(facts),
        input_summary=f"result {result.id} ({result.outcome}) of experiment #{experiment.seq}",
        max_tokens=400,
        temperature=0.3,
        settings=settings,
        provider=provider,
        is_demo=bool(result.is_demo),
    )

    if not outcome.ok or not outcome.text:
        if commit:
            await session.commit()
        return WriterOutcome(
            ok=False, error=outcome.error, run_id=outcome.run_id, cost_usd=outcome.cost_usd
        )

    text = outcome.text.strip().strip('"')
    check = check_draft(text, facts, outcome=result.outcome)

    if not check.ok:
        # The draft is not stored. A refusal with reasons is a better artefact
        # than a post nobody can verify.
        session.add(
            SystemEvent(
                seq=await _next_seq(session),
                event_type=str(EventType.ERROR),
                message=f"writer draft refused: {'; '.join(check.reasons)}",
                level="WARN",
                ref_type="experiment_result",
                ref_id=result.id,
                occurred_at=utcnow(),
                is_demo=bool(result.is_demo),
            )
        )
        await session.flush()
        if commit:
            await session.commit()
        return WriterOutcome(
            ok=False,
            text=text,
            reasons=check.reasons,
            run_id=outcome.run_id,
            cost_usd=outcome.cost_usd,
        )

    draft = ContentDraft(
        content_type=str(content_type_for(result.outcome)),
        body=text,
        status="PENDING",
        source_kind="experiment_result",
        source_id=result.id,
        reviewer_notes=(
            f"written by {WRITER_SOURCE} from result {result.id}; every number checked "
            "against that row before storing"
        ),
        is_demo=bool(result.is_demo),
    )
    session.add(draft)
    await session.flush()

    session.add(
        SystemEvent(
            seq=await _next_seq(session),
            event_type=str(EventType.DRAFT_CREATED),
            message=f"writer drafted a {content_type_for(result.outcome)} post",
            level="INFO",
            ref_type="content_draft",
            ref_id=draft.id,
            occurred_at=utcnow(),
            is_demo=bool(result.is_demo),
        )
    )
    await session.flush()
    if commit:
        await session.commit()

    return WriterOutcome(
        ok=True,
        draft_id=draft.id,
        text=text,
        run_id=outcome.run_id,
        cost_usd=outcome.cost_usd,
    )


async def _next_seq(session: AsyncSession) -> int:
    from sqlalchemy import func

    return int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1
