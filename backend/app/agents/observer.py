"""The observer agent.

There is a hard line here, and it is worth stating before the code: **this agent
does not detect anything.** Detection is deterministic and stays that way — a
threshold crossing, a named detector, a recorded score. What a threshold cannot
produce is a sentence a person can read, and that is the whole of this agent's
job: given an anomaly the detectors already fired, say in one line what it looks
like, using only the numbers the detector recorded.

So it runs *after* the pipeline, never inside it. It can add a reading to an
anomaly. It cannot create one, suppress one, or change a score. If the model is
unavailable the anomaly keeps the deterministic explanation it was stored with,
which is already a complete description — the model adds legibility, not fact.

Every number in the reading is checked against the anomaly's own baseline and
measured values. A reading citing a figure the detector did not record is
dropped, not stored with a caveat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import run_agent
from app.agents.guards import MARKET_CLAIMS, ungrounded_numbers
from app.core.config import Settings, get_settings
from app.models import Anomaly, Observation
from app.providers.model import ModelProvider

OBSERVER_VERSION = "observer-v1"

MAX_READING_CHARS = 240

SYSTEM = """You are the observer for GODGOD, an autonomous research system
watching Solana meme tokens.

A deterministic detector has already fired. You are given what it measured, what
it compared against, and the thresholds it used. You did not find this and you
are not being asked whether it is real — it is recorded either way.

Write one short line, lowercase, describing what the measurement looks like, for
a reader who will not open the numbers. Name the token, say what moved, and say
what it moved against.

Rules:
- Use only numbers present in the measurement you were given.
- Describe what was measured. Never say what it means for the price, never say
  what will happen next, never suggest an action.
- An unusual measurement is not evidence of anything. "unusual" is the strongest
  word available to you.
- No hype, no emoji, no exclamation.

Answer with the line only. No JSON, no quotes, no preamble."""


@dataclass
class ObserverOutcome:
    ok: bool
    reading: str | None = None
    anomaly_id: str | None = None
    reasons: list[str] = field(default_factory=list)
    """Why a reading was refused, when it was."""
    run_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reading": self.reading,
            "anomaly_id": self.anomaly_id,
            "reasons": self.reasons,
            "run_id": self.run_id,
            "cost_usd": self.cost_usd,
            "error": self.error,
            "version": OBSERVER_VERSION,
        }


def facts_for(anomaly: Anomaly, observation: Observation | None) -> dict[str, Any]:
    """Exactly what the observer is allowed to know, and to cite."""
    baseline = dict(anomaly.baseline or {})
    thresholds = baseline.pop("thresholds", None)
    facts: dict[str, Any] = {
        "token": observation.subject_ref if observation else None,
        "detector_summary": observation.summary if observation else None,
        "anomaly_type": anomaly.anomaly_type,
        "detector": anomaly.detector,
        "score": anomaly.score,
    }
    facts.update({f"baseline_{key}": value for key, value in baseline.items()})
    facts.update({f"measured_{key}": value for key, value in (anomaly.measured or {}).items()})
    if isinstance(thresholds, dict):
        facts.update({f"threshold_{key}": value for key, value in thresholds.items()})
    return facts


def check_reading(text: str, facts: dict[str, Any]) -> list[str]:
    """Everything that can be refused without asking anyone's opinion."""
    reasons: list[str] = []
    stripped = text.strip()

    if not stripped:
        reasons.append("the reading is empty")
    if len(stripped) > MAX_READING_CHARS:
        reasons.append(f"{len(stripped)} characters, over the {MAX_READING_CHARS} limit")

    lowered = stripped.lower()
    for claim in MARKET_CLAIMS:
        if claim in lowered:
            reasons.append(f"the reading says '{claim}', which asserts something unmeasured")

    invented = ungrounded_numbers(stripped, facts)
    if invented:
        reasons.append(
            f"the reading cites {', '.join(invented)}, which the detector did not record"
        )
    return reasons


async def read_anomaly(
    session: AsyncSession,
    anomaly_id: str,
    *,
    settings: Settings | None = None,
    provider: ModelProvider | None = None,
    commit: bool = True,
) -> ObserverOutcome:
    """Add a plain-language reading to an anomaly. Never changes the anomaly."""
    settings = settings or get_settings()

    anomaly = await session.scalar(select(Anomaly).where(Anomaly.id == anomaly_id))
    if anomaly is None:
        return ObserverOutcome(ok=False, reasons=["anomaly not found"])

    observation = (
        await session.scalar(
            select(Observation).where(Observation.id == anomaly.observation_id)
        )
        if anomaly.observation_id
        else None
    )
    facts = facts_for(anomaly, observation)

    agent = await run_agent(
        session,
        name="observer",
        role="MODEL_FAST",
        system=SYSTEM,
        prompt=(
            "measurement:\n"
            + "\n".join(f"- {key}: {value}" for key, value in facts.items() if value is not None)
            + "\n\nwrite the line."
        ),
        input_summary=f"anomaly {anomaly.id} ({anomaly.detector})",
        max_tokens=200,
        settings=settings,
        provider=provider,
        is_demo=bool(anomaly.is_demo),
    )

    if not agent.ok or not agent.text:
        return ObserverOutcome(
            ok=False,
            anomaly_id=anomaly.id,
            reasons=["no model reading was produced"],
            run_id=agent.run_id,
            cost_usd=agent.cost_usd,
            error=agent.error,
        )

    reading = agent.text.strip()
    reasons = check_reading(reading, facts)
    if reasons:
        return ObserverOutcome(
            ok=False,
            anomaly_id=anomaly.id,
            reasons=reasons,
            run_id=agent.run_id,
            cost_usd=agent.cost_usd,
        )

    # Stored beside the measurement, never over it. The detector's own
    # explanation is what the anomaly means; this is how it reads.
    if observation is not None:
        payload = dict(observation.payload or {})
        payload["observer_reading"] = reading
        payload["observer_version"] = OBSERVER_VERSION
        observation.payload = payload
        await session.flush()
        if commit:
            await session.commit()

    return ObserverOutcome(
        ok=True,
        reading=reading,
        anomaly_id=anomaly.id,
        run_id=agent.run_id,
        cost_usd=agent.cost_usd,
    )
