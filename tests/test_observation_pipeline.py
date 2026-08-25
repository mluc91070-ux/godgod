"""The pipeline end to end, against the synthetic dataset.

The dataset plants one pattern per token and one control that must stay
silent, so these tests check detection *and* restraint.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import (
    AgentRun,
    Anomaly,
    Memory,
    Observation,
    SocialPost,
    SystemEvent,
    Token,
    TokenSnapshot,
)
from app.providers.source import FixtureObservationSource
from app.services.observation import ObservationPipeline, run_backfill
from app.services.observation.pipeline import PIPELINE_RUN_NAME


@pytest_asyncio.fixture
async def backfilled(session, settings):
    """One full replay of the synthetic series."""
    return await run_backfill(session, source=FixtureObservationSource(), settings=settings)


async def _anomaly_types_by_symbol(session) -> dict[str, set[str]]:
    rows = (
        await session.execute(
            select(Observation.summary, Anomaly.anomaly_type).join(
                Anomaly, Anomaly.observation_id == Observation.id
            )
        )
    ).all()
    found: dict[str, set[str]] = {}
    for summary, anomaly_type in rows:
        symbol = summary.split(":")[0].strip()
        found.setdefault(symbol, set()).add(anomaly_type)
    return found


async def test_backfill_finds_every_planted_pattern(session, backfilled):
    found = await _anomaly_types_by_symbol(session)

    assert "VOLUME_ACCELERATION" in found["SURGE"]
    assert "LIQUIDITY_CHANGE" in found["DRAIN"]
    assert "WALLET_CONCENTRATION_CHANGE" in found["WHALE"]
    assert "SOCIAL_ONCHAIN_DIVERGENCE" in found["BUZZ"]
    assert "TOKEN_SURVIVAL_ANOMALY" in found["OLD"]
    assert "NARRATIVE_ACCELERATION" in found["narrative"]


async def test_the_control_token_produces_no_anomaly(session, backfilled):
    """FLAT is the point of the dataset: a detector that fires on it is broken."""
    found = await _anomaly_types_by_symbol(session)
    assert "FLAT" not in found


async def test_no_model_is_called_anywhere_in_the_pipeline(session, backfilled):
    observations = (await session.scalars(select(Observation))).all()
    assert observations
    assert all(row.llm_reviewed is False for row in observations)
    assert all(report.as_dict()["llm_calls"] == 0 for report in backfilled)


async def test_ingestion_is_exact_and_not_duplicated(session, backfilled):
    """6 tokens x 24 hourly measurements, stored once each."""
    assert await session.scalar(select(func.count()).select_from(Token)) == 6
    assert await session.scalar(select(func.count()).select_from(TokenSnapshot)) == 144

    posts = await session.scalar(select(func.count()).select_from(SocialPost))
    distinct = await session.scalar(select(func.count(func.distinct(SocialPost.external_id))))
    assert posts == distinct


async def test_replaying_the_same_period_adds_nothing(session, settings, backfilled):
    """The cooldown makes the pipeline idempotent over a period."""
    before = await session.scalar(select(func.count()).select_from(Anomaly))
    await run_backfill(session, source=FixtureObservationSource(), settings=settings)
    after = await session.scalar(select(func.count()).select_from(Anomaly))
    assert after == before


async def test_every_anomaly_records_its_detector_and_thresholds(session, backfilled):
    anomalies = (await session.scalars(select(Anomaly))).all()
    assert anomalies
    for anomaly in anomalies:
        assert anomaly.detector.endswith("-v1")
        assert anomaly.score is not None and anomaly.score > 0.0
        assert anomaly.baseline is not None
        assert anomaly.measured is not None


async def test_scores_are_bounded_and_meaningful(session, backfilled):
    observations = (await session.scalars(select(Observation))).all()
    for row in observations:
        assert 0.0 <= row.novelty_score <= 1.0
        assert 0.0 <= row.importance <= 1.0
        assert 0.0 <= row.confidence <= 1.0


async def test_repeats_score_lower_novelty_than_first_sightings(session, backfilled):
    """The second time the same thing is said, it is less novel."""
    narrative = (
        await session.scalars(
            select(Observation)
            .where(Observation.subject_type == "term")
            .order_by(Observation.seq)
        )
    ).all()
    if len(narrative) < 2:
        pytest.skip("need at least two narrative observations")
    assert narrative[0].novelty_score > narrative[-1].novelty_score


async def test_the_cheap_filter_rejects_far_more_than_it_passes(session, backfilled):
    """This ratio is the cost architecture: deterministic gates first."""
    dropped = sum(sum(report.dropped.values()) for report in backfilled)
    created = sum(report.observations_created for report in backfilled)
    assert dropped > created
    reasons = {key for report in backfilled for key in report.dropped}
    assert reasons, "every rejection must be counted under a named reason"


async def test_important_observations_reach_memory(session, backfilled, settings):
    memories = (
        await session.scalars(select(Memory).where(Memory.memory_type == "OBSERVATION"))
    ).all()
    assert memories
    for memory in memories:
        assert memory.ref_type == "observation"
        assert memory.embedding is not None
        assert memory.meta["importance"] >= settings.observation_memory_importance_floor


async def test_events_are_emitted_for_observations_and_anomalies(session, backfilled):
    events = (await session.scalars(select(SystemEvent))).all()
    types = {event.event_type for event in events}
    assert "OBSERVATION" in types
    assert "ANOMALY" in types


async def test_the_run_is_recorded_with_a_null_model_and_zero_cost(session, backfilled):
    runs = (
        await session.scalars(select(AgentRun).where(AgentRun.agent_name == PIPELINE_RUN_NAME))
    ).all()
    assert runs
    for run in runs:
        assert run.model is None, "no model was called, so none is recorded"
        assert run.estimated_cost_usd == 0.0
        assert run.status == "OK"


async def test_a_single_cycle_only_sees_its_own_window(session, settings):
    """A surge from twelve hours ago is, correctly, no longer news."""
    source = FixtureObservationSource()
    report = await ObservationPipeline(source=source, settings=settings).run(session)

    assert report.as_of is not None
    observations = (await session.scalars(select(Observation))).all()
    for row in observations:
        assert row.observed_at.replace(tzinfo=None) == report.as_of.replace(tzinfo=None)


async def test_everything_the_pipeline_writes_is_flagged_demo(session, backfilled):
    for model in (Token, TokenSnapshot, Observation, Anomaly, SocialPost):
        rows = (await session.scalars(select(model))).all()
        assert rows
        assert all(row.is_demo for row in rows), f"{model.__tablename__} came from fixtures"
