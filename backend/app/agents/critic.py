"""The critic agent.

The deterministic critic in `services/research/critic.py` runs first and always.
It answers the mechanical questions — is the sample big enough, are the rows
independent, did the outcome get read after exposure, was the declared control
applied. This agent answers the one a check cannot: *given everything recorded
about how this was measured, is there an objection nobody encoded?*

**It can only be stricter.** A model reading is allowed to add an objection and
to downgrade a verdict; it can never lift one. PASS → NEEDS_MORE_DATA → FAIL is
the only direction it moves in. That is not caution, it is the rule that makes
the agent safe to add at all: a deterministic FAIL that a model could argue away
would make every gate in the system advisory.

The model is given the recorded numbers and nothing else — no database, no
dataset. Any figure it puts in its objection is checked against those numbers,
and an objection containing an invented one is dropped rather than stored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.base import run_agent
from app.agents.guards import ungrounded_numbers
from app.core.config import Settings, get_settings
from app.core.enums import CriticVerdict
from app.models import Experiment, ExperimentResult
from app.providers.model import ModelProvider

CRITIC_AGENT_VERSION = "critic-agent-v1"

SEVERITY = {
    str(CriticVerdict.PASS): 0,
    str(CriticVerdict.NEEDS_MORE_DATA): 1,
    str(CriticVerdict.FAIL): 2,
}
"""Ordered so a verdict can be compared. The agent may raise, never lower."""

SYSTEM = """You are the critic for GODGOD, an autonomous research system. You are
given everything recorded about one experiment: the question, the falsification
rule written before the data was seen, the measured rates, the sample sizes, the
rows that could not be built, and the verdicts the deterministic checks already
returned.

Your only question is: why might this result be wrong?

You may raise the severity of the verdict. You may never lower it. If the
deterministic checks already say FAIL, your verdict is FAIL.

Objections worth raising are ones a threshold cannot see: a comparison whose
exposed group is defined so narrowly it cannot mean what the question asks, a
baseline that is not a baseline, an outcome that would be true of almost any
row, a period short enough that one token's behaviour is the whole effect.

Do not restate an objection the deterministic checks already made. Do not
mention a number that is not in the facts you were given.

Answer with JSON only:
{"verdict": "PASS" | "NEEDS_MORE_DATA" | "FAIL",
 "objection": "<one short sentence, lowercase, or empty if you have none>"}"""


@dataclass
class CriticOutcome:
    verdict: str
    """The combined verdict: the stricter of deterministic and model."""
    deterministic_verdict: str = str(CriticVerdict.PASS)
    model_verdict: str | None = None
    """None when no model read it. Not the same as a PASS."""
    objection: str | None = None
    dropped: list[str] = field(default_factory=list)
    """Objections thrown away, and why. Never silently discarded."""
    run_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "deterministic_verdict": self.deterministic_verdict,
            "model_verdict": self.model_verdict,
            "objection": self.objection,
            "dropped": self.dropped,
            "run_id": self.run_id,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "version": CRITIC_AGENT_VERSION,
        }


def strictest(*verdicts: str | None) -> str:
    """The harshest verdict among those given. Unknown values are ignored."""
    known = [verdict for verdict in verdicts if verdict in SEVERITY]
    if not known:
        return str(CriticVerdict.NEEDS_MORE_DATA)
    return max(known, key=lambda verdict: SEVERITY[verdict])


def parse_answer(text: str) -> tuple[str | None, str | None]:
    """Read the model's JSON without trusting its shape."""
    body = text.strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1:
        return None, None
    try:
        parsed = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None, None
    verdict = str(parsed.get("verdict", "")).upper()
    if verdict not in SEVERITY:
        return None, None
    objection = parsed.get("objection")
    text_out = str(objection).strip() if objection else None
    return verdict, text_out or None


def facts_for_critic(experiment: Experiment, result: ExperimentResult) -> dict[str, Any]:
    """Exactly what the critic is allowed to know, and to cite."""
    hypothesis = experiment.hypothesis
    metrics = result.metrics or {}
    return {
        "question": hypothesis.question if hypothesis else experiment.title,
        "falsification_condition": (
            hypothesis.falsification_condition if hypothesis else None
        ),
        "population": hypothesis.population if hypothesis else None,
        "baseline": hypothesis.baseline if hypothesis else None,
        "timeframe": hypothesis.timeframe if hypothesis else None,
        "method": experiment.method,
        "outcome": result.outcome,
        "summary": result.summary,
        "rate_exposed": metrics.get("rate_exposed"),
        "rate_control": metrics.get("rate_control"),
        "difference_pp": metrics.get("difference_pp"),
        "n_exposed": metrics.get("n_exposed"),
        "n_control": metrics.get("n_control"),
        "distinct_tokens": metrics.get("distinct_tokens"),
        "p_value": result.p_value,
        "excluded_rows": metrics.get("excluded_rows"),
        "deterministic_checks": result.critic_checks,
        "deterministic_notes": result.critic_notes,
        "limitations": result.limitations,
    }


async def critique_result(
    session: AsyncSession,
    result_id: str,
    *,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    commit: bool = True,
) -> CriticOutcome:
    settings = settings or get_settings()

    result = await session.scalar(
        select(ExperimentResult).where(ExperimentResult.id == result_id)
    )
    if result is None:
        return CriticOutcome(
            verdict=str(CriticVerdict.FAIL),
            deterministic_verdict=str(CriticVerdict.FAIL),
            dropped=["result not found"],
        )

    experiment = await session.scalar(
        select(Experiment)
        .options(selectinload(Experiment.hypothesis))
        .where(Experiment.id == result.experiment_id)
    )
    if experiment is None:
        return CriticOutcome(
            verdict=str(CriticVerdict.FAIL),
            deterministic_verdict=str(CriticVerdict.FAIL),
            dropped=["result has no experiment to check against"],
        )

    deterministic = result.critic_verdict or str(CriticVerdict.NEEDS_MORE_DATA)
    facts = facts_for_critic(experiment, result)

    agent = await run_agent(
        session,
        name="critic",
        role="MODEL_CRITIC",
        system=SYSTEM,
        prompt=(
            "facts:\n"
            + "\n".join(f"- {key}: {value}" for key, value in facts.items())
            + "\n\nanswer with the json object."
        ),
        input_summary=f"result {result.id} of experiment {experiment.id}",
        max_tokens=300,
        settings=settings,
        provider=provider,
        is_demo=bool(result.is_demo),
    )

    model_verdict: str | None = None
    objection: str | None = None
    dropped: list[str] = []

    if agent.ok and agent.text:
        model_verdict, objection = parse_answer(agent.text)
        if model_verdict is None:
            dropped.append("the critic model did not return a usable verdict")
        elif SEVERITY[model_verdict] < SEVERITY.get(deterministic, 1):
            # Recorded, not obeyed. A model arguing a deterministic failure away
            # is the one thing this agent must never be able to do.
            dropped.append(
                f"the model answered {model_verdict} against a deterministic "
                f"{deterministic}; a model verdict can only be stricter"
            )
        if objection:
            invented = ungrounded_numbers(objection, facts)
            if invented:
                dropped.append(
                    f"objection dropped: it cites {', '.join(invented)}, "
                    "which is not in the recorded result"
                )
                objection = None

    verdict = strictest(deterministic, model_verdict)

    outcome = CriticOutcome(
        verdict=verdict,
        deterministic_verdict=deterministic,
        model_verdict=model_verdict,
        objection=objection,
        dropped=dropped,
        run_id=agent.run_id,
        cost_usd=agent.cost_usd,
        error=agent.error,
    )
    await _store(session, result, outcome, commit=commit)
    return outcome


async def _store(
    session: AsyncSession, result: ExperimentResult, outcome: CriticOutcome, *, commit: bool
) -> None:
    """Write the verdict back, keeping the deterministic record readable.

    The checks dict gains the agent's answer under its own keys rather than
    overwriting any check: which objection came from a threshold and which from
    a model has to stay separable after the fact.
    """
    checks = dict(result.critic_checks or {})
    checks["model_verdict"] = outcome.model_verdict or "NOT_REVIEWED"
    checks["agent_version"] = CRITIC_AGENT_VERSION
    result.critic_checks = checks
    result.critic_verdict = outcome.verdict

    additions = [note for note in (outcome.objection, *outcome.dropped) if note]
    if outcome.model_verdict is None and not additions:
        additions.append(
            f"no model read this result ({CRITIC_AGENT_VERSION}); "
            "the deterministic checks stand alone."
        )
    if additions:
        existing = result.critic_notes or ""
        result.critic_notes = f"{existing} {' '.join(additions)}".strip()[:4000]

    await session.flush()
    if commit:
        await session.commit()
