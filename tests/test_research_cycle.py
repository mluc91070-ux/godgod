"""The research cycle end to end, on the synthetic series.

Checks the chain the public pages render: anomaly → memory → hypothesis →
dataset → experiment → critic → result → memory → draft, and that nothing in
it calls a model or invents a number.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.enums import (
    ContentType,
    CriticVerdict,
    ExperimentStatus,
    HypothesisStatus,
    ResultOutcome,
    TraceStepKind,
)
from app.models import (
    AgentRun,
    ContentDraft,
    Experiment,
    ExperimentResult,
    Hypothesis,
    Memory,
    Pattern,
    ResearchTrace,
    TraceStep,
)
from app.providers.source import FixtureObservationSource
from app.services.observation import run_backfill
from app.services.research import RESEARCH_RUN_NAME, run_research_cycle
from app.services.research.cycle import DRAFT_SOURCE


@pytest_asyncio.fixture
async def researched(session, settings):
    """Replay the series, then run one research cycle over what it found."""
    await run_backfill(session, source=FixtureObservationSource(), settings=settings)
    report = await run_research_cycle(session, settings=settings)
    return report


async def test_cycle_turns_anomalies_into_tested_hypotheses(session, researched):
    assert researched.hypotheses_created > 0
    assert researched.experiments_run == researched.hypotheses_created
    total = (
        researched.supported + researched.rejected + researched.inconclusive
    )
    assert total == researched.experiments_run


async def test_cycle_calls_no_model(session, researched):
    assert researched.as_dict()["llm_calls"] == 0
    runs = (
        await session.scalars(
            select(AgentRun).where(AgentRun.agent_name == RESEARCH_RUN_NAME)
        )
    ).all()
    assert runs
    for run in runs:
        assert run.model is None
        assert run.estimated_cost_usd == 0.0


async def test_every_experiment_records_how_to_rerun_it(session, researched):
    experiments = (await session.scalars(select(Experiment))).all()
    assert experiments
    for experiment in experiments:
        if experiment.status != str(ExperimentStatus.COMPLETED):
            continue
        assert experiment.dataset_version
        assert len(experiment.dataset_hash) == 64
        assert experiment.parameters
        assert experiment.method
        assert experiment.sample_size is not None


async def test_every_result_carries_a_critic_verdict(session, researched):
    results = (await session.scalars(select(ExperimentResult))).all()
    assert results
    valid = {str(item) for item in CriticVerdict}
    for result in results:
        assert result.critic_verdict in valid
        assert result.critic_checks
        assert result.critic_notes
        assert result.outcome in {str(item) for item in ResultOutcome}


async def test_no_hypothesis_is_supported_without_a_passing_critic(session, researched):
    rows = (
        await session.execute(
            select(Hypothesis.status, ExperimentResult.critic_verdict)
            .join(Experiment, Experiment.hypothesis_id == Hypothesis.id)
            .join(ExperimentResult, ExperimentResult.experiment_id == Experiment.id)
        )
    ).all()
    assert rows
    for status, verdict in rows:
        if status == str(HypothesisStatus.SUPPORTED):
            assert verdict == str(CriticVerdict.PASS)


async def test_a_result_without_significance_is_never_supported(session, researched):
    results = (await session.scalars(select(ExperimentResult))).all()
    for result in results:
        if result.outcome == str(ResultOutcome.SUPPORTED):
            assert result.p_value is not None and result.p_value <= 0.05


async def test_memory_is_consulted_before_the_hypothesis_is_written(session, researched):
    hypotheses = (
        await session.scalars(
            select(Hypothesis).where(Hypothesis.origin_observation_id.is_not(None))
        )
    ).all()
    assert hypotheses
    for hypothesis in hypotheses:
        assert "memory_consulted" in (hypothesis.variables or {})


async def test_the_trace_records_the_whole_chain(session, researched):
    traces = (await session.scalars(select(ResearchTrace))).all()
    assert traces
    complete = [trace for trace in traces if trace.completed_at is not None]
    assert complete
    kinds_seen: set[str] = set()
    for trace in complete:
        steps = (
            await session.scalars(
                select(TraceStep)
                .where(TraceStep.trace_id == trace.id)
                .order_by(TraceStep.position)
            )
        ).all()
        assert [step.position for step in steps] == list(range(len(steps)))
        kinds_seen.update(step.kind for step in steps)
    for required in (
        TraceStepKind.OBSERVATION,
        TraceStepKind.ANOMALY,
        TraceStepKind.HYPOTHESIS,
        TraceStepKind.DATASET,
        TraceStepKind.EXPERIMENT,
        TraceStepKind.CRITIC,
        TraceStepKind.RESULT,
    ):
        assert str(required) in kinds_seen


async def test_drafts_are_marked_as_templated_and_never_published(session, researched):
    drafts = (
        await session.scalars(
            select(ContentDraft).where(ContentDraft.source_kind == "experiment")
        )
    ).all()
    assert drafts
    for draft in drafts:
        assert draft.status == "PENDING"
        assert draft.approved_at is None
        assert draft.source_id
        assert DRAFT_SOURCE in (draft.reviewer_notes or "")
        assert draft.content_type in {str(item) for item in ContentType}


async def test_a_second_cycle_does_not_ask_the_same_question_twice(session, settings, researched):
    before = await session.scalar(select(func.count()).select_from(Hypothesis))
    second = await run_research_cycle(session, settings=settings)
    after = await session.scalar(select(func.count()).select_from(Hypothesis))
    assert after == before
    assert second.hypotheses_created == 0
    assert second.experiments_run == 0


async def test_patterns_track_support_and_contradiction(session, researched):
    patterns = (await session.scalars(select(Pattern))).all()
    assert patterns
    for pattern in patterns:
        assert pattern.support_count >= 0
        assert pattern.contradiction_count >= 0
        assert pattern.description


async def test_the_cycle_writes_what_it_learned_to_memory(session, researched):
    assert researched.memories_written > 0
    memories = (
        await session.scalars(select(Memory).where(Memory.ref_type == "experiment"))
    ).all()
    assert memories
    for memory in memories:
        assert memory.content
        assert memory.ref_id


async def test_skipped_reasons_are_named_never_silent(session, researched):
    for reason, count in researched.skipped.items():
        assert reason and reason.replace("_", "").isalnum()
        assert count > 0


@pytest.mark.parametrize("endpoint", ["/api/hypotheses", "/api/experiments", "/api/traces"])
async def test_research_endpoints_serve_the_cycle_output(client, admin_headers, endpoint):
    run = await client.post("/api/admin/research/run", headers=admin_headers)
    assert run.status_code == 200
    assert run.json()["llm_calls"] == 0

    listing = await client.get(endpoint)
    assert listing.status_code == 200
    assert listing.json()["total"] >= 0


async def test_the_research_run_endpoint_requires_the_admin_token(client):
    response = await client.post("/api/admin/research/run")
    assert response.status_code in (401, 403)


async def test_status_reports_the_research_engine_honestly(client):
    body = (await client.get("/api/status")).json()
    research = body["research"]
    assert research["implemented"] is True
    assert research["llm_in_loop"] is False
    assert research["hypothesis_templates"] > 0
    assert research["critic_checks"]
    assert research["unit_of_analysis"] == "token-measurement"


async def test_a_live_run_is_not_logged_as_a_demo_run(session, settings) -> None:
    """The run log and the artefacts must agree about what happened.

    This flag was hardcoded `True`. In production it labelled every real
    research run as demo while the hypotheses those same runs wrote were
    correctly marked real, so the run log said the site had never researched
    anything.
    """
    settings.demo_mode = False
    await run_research_cycle(session, settings=settings)

    runs = (
        await session.scalars(select(AgentRun).where(AgentRun.agent_name == RESEARCH_RUN_NAME))
    ).all()
    assert runs
    assert all(run.is_demo is False for run in runs)


async def test_a_demo_run_still_says_demo(session, settings) -> None:
    settings.demo_mode = True
    await run_research_cycle(session, settings=settings)

    runs = (
        await session.scalars(select(AgentRun).where(AgentRun.agent_name == RESEARCH_RUN_NAME))
    ).all()
    assert runs
    assert all(run.is_demo is True for run in runs)
