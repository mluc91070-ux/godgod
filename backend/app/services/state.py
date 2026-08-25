"""Derived system state.

The homepage visualization is driven by these numbers. They are computed
from stored rows only — never randomised, never simulated.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import EventType, SystemState
from app.models import (
    Anomaly,
    ContentDraft,
    Experiment,
    ExperimentResult,
    Hypothesis,
    Memory,
    Observation,
    Pattern,
    SystemEvent,
)
from app.models.base import utcnow
from app.schemas.common import CountsInfo, LiveResponse

EVENT_STATE: dict[str, SystemState] = {
    EventType.SYSTEM_START: SystemState.IDLE,
    EventType.OBSERVATION: SystemState.OBSERVING,
    EventType.ANOMALY: SystemState.ANALYZING,
    EventType.MEMORY_SEARCH: SystemState.ANALYZING,
    EventType.HYPOTHESIS_CREATED: SystemState.HYPOTHESIZING,
    EventType.EXPERIMENT_STARTED: SystemState.TESTING,
    EventType.EXPERIMENT_PROGRESS: SystemState.TESTING,
    EventType.EXPERIMENT_COMPLETED: SystemState.TESTING,
    EventType.CRITIC_RESULT: SystemState.ANALYZING,
    EventType.HYPOTHESIS_REJECTED: SystemState.REJECTED,
    EventType.HYPOTHESIS_SUPPORTED: SystemState.SUPPORTED,
    EventType.MEMORY_UPDATED: SystemState.LEARNING,
    EventType.DRAFT_CREATED: SystemState.LEARNING,
    EventType.ERROR: SystemState.IDLE,
}

ACTIVITY_WINDOW = timedelta(hours=1)
ACTIVITY_SATURATION = 12
"""Events per hour that count as full activity."""


async def _count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def get_counts(session: AsyncSession) -> CountsInfo:
    return CountsInfo(
        observations=await _count(session, Observation),
        anomalies=await _count(session, Anomaly),
        hypotheses=await _count(session, Hypothesis),
        experiments=await _count(session, Experiment),
        results=await _count(session, ExperimentResult),
        patterns=await _count(session, Pattern),
        memories=await _count(session, Memory),
        drafts=await _count(session, ContentDraft),
        events=await _count(session, SystemEvent),
    )


async def get_state(session: AsyncSession) -> SystemState:
    last = await session.scalar(
        select(SystemEvent).order_by(SystemEvent.occurred_at.desc()).limit(1)
    )
    if last is None:
        return SystemState.IDLE
    return EVENT_STATE.get(last.event_type, SystemState.IDLE)


async def get_live(session: AsyncSession) -> LiveResponse:
    last_event = await session.scalar(
        select(SystemEvent).order_by(SystemEvent.occurred_at.desc()).limit(1)
    )
    observation = await session.scalar(
        select(Observation).order_by(Observation.observed_at.desc()).limit(1)
    )
    hypothesis = await session.scalar(
        select(Hypothesis).order_by(Hypothesis.created_at.desc(), Hypothesis.seq.desc()).limit(1)
    )
    experiment = await session.scalar(
        select(Experiment).order_by(Experiment.created_at.desc(), Experiment.seq.desc()).limit(1)
    )

    # Activity is measured in the hour preceding the most recent event, so a
    # frozen demo dataset reports the activity it actually had.
    activity = 0.0
    if last_event is not None:
        since = last_event.occurred_at - ACTIVITY_WINDOW
        recent = int(
            await session.scalar(
                select(func.count())
                .select_from(SystemEvent)
                .where(SystemEvent.occurred_at >= since)
            )
            or 0
        )
        activity = min(1.0, recent / ACTIVITY_SATURATION)

    is_demo = bool(last_event.is_demo) if last_event is not None else bool(
        observation.is_demo if observation is not None else False
    )

    return LiveResponse(
        state=str(await get_state(session)),
        is_demo=is_demo,
        updated_at=last_event.occurred_at if last_event else utcnow(),
        current_observation=(
            {
                "id": observation.id,
                "seq": observation.seq,
                "summary": observation.summary,
                "observed_at": observation.observed_at.isoformat(),
                "novelty_score": observation.novelty_score,
            }
            if observation
            else None
        ),
        current_hypothesis=(
            {
                "id": hypothesis.id,
                "seq": hypothesis.seq,
                "question": hypothesis.question,
                "status": hypothesis.status,
                "confidence": hypothesis.confidence,
            }
            if hypothesis
            else None
        ),
        current_experiment=(
            {
                "id": experiment.id,
                "seq": experiment.seq,
                "title": experiment.title,
                "status": experiment.status,
                "sample_size": experiment.sample_size,
            }
            if experiment
            else None
        ),
        last_event=(
            {
                "event_type": last_event.event_type,
                "message": last_event.message,
                "occurred_at": last_event.occurred_at.isoformat(),
            }
            if last_event
            else None
        ),
        activity=activity,
        novelty=observation.novelty_score if observation else None,
        confidence=hypothesis.confidence if hypothesis else None,
        streaming=False,
    )
