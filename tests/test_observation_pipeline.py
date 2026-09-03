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
    """7 tokens x 24 hourly measurements, stored once each."""
    assert await session.scalar(select(func.count()).select_from(Token)) == 7
    assert await session.scalar(select(func.count()).select_from(TokenSnapshot)) == 168

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


async def test_the_sampling_frame_survives_an_observation_run(session, settings) -> None:
    """The pipeline reads the collector's tokens. It must not rewrite them.

    Measured in production: after the loop started running observation live
    every quarter hour, 144 of 144 tokens read as `database-live` instead of
    the frame that found them. The frame is the whole basis for stratifying an
    experiment by population, so losing it is not cosmetic — it silently
    empties every comparison that depends on it.
    """
    from datetime import UTC, datetime, timedelta

    from app.providers.source import DatabaseObservationSource
    from app.services.chain import PROMOTED

    token = Token(
        address="FrameSurvives1111",
        symbol="FRM",
        name="a promoted token",
        source=PROMOTED,
        is_demo=False,
    )
    session.add(token)
    await session.flush()

    # Without measurements the pipeline never reaches the upsert, so this is
    # what makes the test exercise the path that lost the frame.
    now = datetime.now(UTC)
    for index in range(8):
        session.add(
            TokenSnapshot(
                token_id=token.id,
                observed_at=now - timedelta(minutes=15 * (8 - index)),
                liquidity_usd=40_000.0,
                volume_usd=90_000.0,
                source="test",
                is_demo=False,
            )
        )
    await session.flush()

    report = await ObservationPipeline(
        source=DatabaseObservationSource(session), settings=settings
    ).run(session)
    await session.refresh(token)

    assert report.subjects_examined == 1  # the token really went through
    assert token.source == PROMOTED


async def test_a_known_field_is_never_replaced_by_a_null(session, settings) -> None:
    """A later run that learned less must not erase what an earlier one knew."""
    from datetime import UTC, datetime, timedelta

    from app.providers.source import ObservationSource, TokenRef

    now = datetime.now(UTC)
    series = [
        {
            "observed_at": now - timedelta(minutes=15 * (8 - index)),
            "liquidity_usd": 40_000.0,
            "volume_usd": 90_000.0,
        }
        for index in range(8)
    ]

    class Forgetful(ObservationSource):
        name = "forgetful"
        is_demo = False

        async def list_tokens(self):
            return [
                TokenRef(
                    address="KeepsItsName111",
                    symbol=None,
                    name=None,
                    decimals=None,
                    launch_time=None,
                    launchpad=None,
                )
            ]

        async def get_snapshots(self, address, *, since=None, until=None):
            return list(series)

        async def get_posts(self, address=None, *, since=None, until=None):
            return []

        async def latest_timestamp(self):
            return now

    token = Token(address="KeepsItsName111", symbol="KEEP", name="a name", is_demo=False)
    session.add(token)
    await session.flush()

    report = await ObservationPipeline(source=Forgetful(), settings=settings).run(session)
    await session.refresh(token)

    assert report.subjects_examined == 1
    assert token.symbol == "KEEP"
    assert token.name == "a name"
