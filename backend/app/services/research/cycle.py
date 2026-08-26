"""The research cycle.

    observation → anomaly → memory search → hypothesis → dataset
    → experiment → critic → result → memory → draft

Memory is searched *before* a hypothesis is written, and the memories consulted
are recorded on the hypothesis. Every step appends to an immutable trace, which
is what the public experiment page renders.

Deterministic end to end. No model is called; the drafts produced here are
templated, and say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.core.enums import (
    ContentType,
    EventType,
    ExperimentStatus,
    HypothesisStatus,
    ResultOutcome,
    TraceStepKind,
)
from app.models import (
    AgentRun,
    Anomaly,
    ContentDraft,
    Experiment,
    ExperimentResult,
    Hypothesis,
    Observation,
    Pattern,
    ResearchTrace,
    SystemEvent,
    TraceStep,
)
from app.models.base import utcnow
from app.services.memory import search_memory, store_memory
from app.services.research.critic import CRITIC_VERSION, hypothesis_status, review
from app.services.research.dataset import DATASET_VERSION, build_dataset
from app.services.research.experiments import ExperimentOutcome, evaluate
from app.services.research.templates import TEMPLATES_BY_ANOMALY, TEMPLATES_BY_KEY

RESEARCH_RUN_NAME = "research-pipeline"
DRAFT_SOURCE = "templated-v1"
"""Drafts are filled-in templates. The writer agent is the model version."""


@dataclass
class ResearchReport:
    hypotheses_created: int = 0
    experiments_run: int = 0
    supported: int = 0
    rejected: int = 0
    inconclusive: int = 0
    memories_written: int = 0
    drafts_created: int = 0
    patterns_updated: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "hypotheses_created": self.hypotheses_created,
            "experiments_run": self.experiments_run,
            "supported": self.supported,
            "rejected": self.rejected,
            "inconclusive": self.inconclusive,
            "memories_written": self.memories_written,
            "drafts_created": self.drafts_created,
            "patterns_updated": self.patterns_updated,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
            "llm_calls": 0,
        }


async def _next_seq(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.max(model.seq))) or 0) + 1


async def _event(
    session: AsyncSession,
    *,
    event_type: EventType,
    message: str,
    occurred_at: datetime,
    ref_type: str | None = None,
    ref_id: str | None = None,
    level: str = "INFO",
    is_demo: bool = True,
) -> None:
    session.add(
        SystemEvent(
            seq=await _next_seq(session, SystemEvent),
            event_type=str(event_type),
            message=message,
            level=level,
            ref_type=ref_type,
            ref_id=ref_id,
            occurred_at=occurred_at,
            is_demo=is_demo,
        )
    )
    await session.flush()


async def _add_step(
    session: AsyncSession,
    trace: ResearchTrace,
    *,
    kind: TraceStepKind,
    summary: str,
    occurred_at: datetime,
    ref_type: str | None = None,
    ref_id: str | None = None,
    detail: dict | None = None,
) -> None:
    position = int(
        await session.scalar(
            select(func.count()).select_from(TraceStep).where(TraceStep.trace_id == trace.id)
        )
        or 0
    )
    session.add(
        TraceStep(
            trace_id=trace.id,
            position=position,
            kind=str(kind),
            summary=summary,
            ref_type=ref_type,
            ref_id=ref_id,
            occurred_at=occurred_at,
            detail=detail,
            is_demo=trace.is_demo,
        )
    )
    await session.flush()


# -- PHASE 4: hypotheses ----------------------------------------------------


async def generate_hypotheses(
    session: AsyncSession, *, settings: Settings | None = None, report: ResearchReport
) -> list[Hypothesis]:
    """One hypothesis per unexplained anomaly type, memory consulted first."""
    settings = settings or get_settings()

    observations = (
        await session.scalars(
            select(Observation)
            .options(selectinload(Observation.anomalies))
            .join(Anomaly, Anomaly.observation_id == Observation.id)
            .order_by(Observation.observed_at)
            .distinct()
        )
    ).all()

    existing_templates = {
        (row.variables or {}).get("template")
        for row in (await session.scalars(select(Hypothesis))).all()
    }
    explained = {
        row.origin_observation_id
        for row in (await session.scalars(select(Hypothesis))).all()
        if row.origin_observation_id
    }

    created: list[Hypothesis] = []
    for observation in observations:
        if observation.id in explained:
            continue
        for anomaly in observation.anomalies:
            template = TEMPLATES_BY_ANOMALY.get(anomaly.anomaly_type)
            if template is None:
                report.skipped["no_template_for_anomaly"] = (
                    report.skipped.get("no_template_for_anomaly", 0) + 1
                )
                continue
            if template.key in existing_templates:
                report.skipped["question_already_asked"] = (
                    report.skipped.get("question_already_asked", 0) + 1
                )
                continue

            # Memory before hypothesis: what do I already know about this?
            recalled = await search_memory(
                session,
                f"{anomaly.anomaly_type} {observation.summary}",
                limit=settings.memory_retrieval_limit,
                settings=settings,
            )
            await _event(
                session,
                event_type=EventType.MEMORY_SEARCH,
                message=(
                    f"{len(recalled.hits)} related memories for {anomaly.anomaly_type} "
                    f"({recalled.method})"
                ),
                occurred_at=observation.observed_at,
                is_demo=observation.is_demo,
            )

            hypothesis = Hypothesis(
                seq=await _next_seq(session, Hypothesis),
                statement=template.statement,
                question=template.question,
                variables={
                    **template.variables,
                    "template": template.key,
                    "trigger_anomaly": anomaly.anomaly_type,
                    "memory_consulted": [hit.memory.id for hit in recalled.hits],
                    "outcome": template.outcome_label,
                },
                population=template.population,
                sample_definition=template.sample_definition,
                timeframe=template.timeframe,
                baseline=template.baseline,
                expected_result=template.expected_result,
                falsification_condition=template.falsification_condition,
                confidence=None,
                status=str(HypothesisStatus.PROPOSED),
                origin_observation_id=observation.id,
                is_demo=observation.is_demo,
            )
            session.add(hypothesis)
            await session.flush()
            existing_templates.add(template.key)
            explained.add(observation.id)
            created.append(hypothesis)
            report.hypotheses_created += 1

            trace = ResearchTrace(
                seq=await _next_seq(session, ResearchTrace),
                title=template.question,
                hypothesis_id=hypothesis.id,
                started_at=observation.observed_at,
                is_demo=observation.is_demo,
            )
            session.add(trace)
            await session.flush()

            await _add_step(
                session,
                trace,
                kind=TraceStepKind.OBSERVATION,
                summary=observation.summary,
                occurred_at=observation.observed_at,
                ref_type="observation",
                ref_id=observation.id,
            )
            await _add_step(
                session,
                trace,
                kind=TraceStepKind.ANOMALY,
                summary=f"{anomaly.anomaly_type} score={anomaly.score:.2f} [{anomaly.detector}]",
                occurred_at=anomaly.detected_at,
                ref_type="anomaly",
                ref_id=anomaly.id,
            )
            await _add_step(
                session,
                trace,
                kind=TraceStepKind.MEMORY_SEARCH,
                summary=(
                    f"{len(recalled.hits)} related memories retrieved before writing the "
                    f"hypothesis ({recalled.method})"
                ),
                occurred_at=observation.observed_at,
                detail={"memory_ids": [hit.memory.id for hit in recalled.hits]},
            )
            await _add_step(
                session,
                trace,
                kind=TraceStepKind.HYPOTHESIS,
                summary=f"#{hypothesis.seq} {template.question}",
                occurred_at=observation.observed_at,
                ref_type="hypothesis",
                ref_id=hypothesis.id,
            )
            await _event(
                session,
                event_type=EventType.HYPOTHESIS_CREATED,
                message=f"#{hypothesis.seq} {template.question}",
                occurred_at=observation.observed_at,
                ref_type="hypothesis",
                ref_id=hypothesis.id,
                is_demo=observation.is_demo,
            )
            break  # one hypothesis per observation

    return created


# -- PHASE 5 + 6: experiment and critic -------------------------------------


def _draft_body(
    hypothesis: Hypothesis, experiment: Experiment, outcome: ExperimentOutcome, verdict: str
) -> tuple[str, ContentType]:
    number = f"#{hypothesis.seq:03d}"
    difference = outcome.metrics.get("difference_pp")

    if outcome.outcome == str(ResultOutcome.REJECTED):
        return (
            f"hypothesis {number}\n\nrejected.\n\n{outcome.summary.split('.')[0].lower()}.",
            ContentType.FAILURE,
        )
    if outcome.outcome == str(ResultOutcome.SUPPORTED):
        return (
            f"hypothesis {number}\n\nsupported, with the critic's objections attached.\n\n"
            f"{difference:+.1f} points, p={outcome.p_value}.",
            ContentType.RESULT,
        )
    return (
        f"experiment #{experiment.seq:06d}\n\n"
        f"{difference:+.1f} points.\n\n"
        f"critic: {verdict.lower().replace('_', ' ')}.\n\n"
        "i can't tell yet.",
        ContentType.EXPERIMENT,
    )


async def _update_pattern(
    session: AsyncSession,
    hypothesis: Hypothesis,
    outcome: ExperimentOutcome,
    report: ResearchReport,
) -> None:
    """A pattern is the accumulated verdict on a question, not a single run."""
    template_key = (hypothesis.variables or {}).get("template", "unknown")
    pattern = await session.scalar(select(Pattern).where(Pattern.name == template_key))
    if pattern is None:
        pattern = Pattern(
            name=template_key,
            description=hypothesis.question,
            status="CANDIDATE",
            first_seen_at=utcnow(),
            is_demo=hypothesis.is_demo,
        )
        session.add(pattern)
        await session.flush()

    if outcome.outcome == str(ResultOutcome.SUPPORTED):
        pattern.support_count += 1
        pattern.status = "CONFIRMED" if pattern.support_count >= 2 else "CANDIDATE"
        pattern.last_confirmed_at = utcnow()
    elif outcome.outcome == str(ResultOutcome.REJECTED):
        pattern.contradiction_count += 1
        pattern.status = "REJECTED"
    pattern.confidence = outcome.confidence
    pattern.evidence_refs = (pattern.evidence_refs or []) + [hypothesis.id]
    report.patterns_updated += 1
    await session.flush()


async def run_experiment_for(
    session: AsyncSession,
    hypothesis: Hypothesis,
    *,
    settings: Settings | None = None,
    report: ResearchReport,
) -> Experiment | None:
    settings = settings or get_settings()
    template = TEMPLATES_BY_KEY.get((hypothesis.variables or {}).get("template", ""))
    if template is None:
        report.skipped["hypothesis_without_template"] = (
            report.skipped.get("hypothesis_without_template", 0) + 1
        )
        return None

    now = utcnow()
    hypothesis.status = str(HypothesisStatus.TESTING)
    await session.flush()

    dataset = await build_dataset(
        session, template, window_hours=settings.observation_window_hours
    )
    outcome = evaluate(dataset, template)
    critique = review(dataset, outcome, template)

    trace = await session.scalar(
        select(ResearchTrace).where(ResearchTrace.hypothesis_id == hypothesis.id)
    )

    experiment = Experiment(
        seq=await _next_seq(session, Experiment),
        hypothesis_id=hypothesis.id,
        title=template.question,
        method=(
            "Token-hour cohort comparison. Exposure is the trigger condition evaluated on a "
            f"{settings.observation_window_hours}h trailing window; the outcome is "
            f"'{template.outcome_label}' read strictly {template.horizon_hours}h later. "
            "Rates are compared pooled and per liquidity stratum with a two-proportion "
            "z-test, then re-checked on a chronological split."
        ),
        features=template.features,
        parameters={
            "window_hours": settings.observation_window_hours,
            "horizon_hours": template.horizon_hours,
            "min_effect_pp": template.min_effect_pp,
            "strata": "liquidity",
        },
        dataset_version=DATASET_VERSION,
        dataset_hash=dataset.hash(),
        sample_size=len(dataset.rows),
        train_period="not applicable (no model fitted)",
        validation_period=(
            f"{dataset.period_start.isoformat()} to {dataset.period_end.isoformat()}"
            if dataset.period_start and dataset.period_end
            else None
        ),
        out_of_sample_period=None,
        status=str(ExperimentStatus.COMPLETED),
        started_at=now,
        completed_at=utcnow(),
        limitations="; ".join(outcome.limitations) or None,
        is_demo=hypothesis.is_demo,
    )
    session.add(experiment)
    await session.flush()
    report.experiments_run += 1

    await _event(
        session,
        event_type=EventType.EXPERIMENT_STARTED,
        message=f"#{experiment.seq:06d} {template.key}, n={len(dataset.rows)} token-hours",
        occurred_at=now,
        ref_type="experiment",
        ref_id=experiment.id,
        is_demo=hypothesis.is_demo,
    )

    result = ExperimentResult(
        experiment_id=experiment.id,
        outcome=outcome.outcome,
        summary=outcome.summary,
        metrics=outcome.metrics,
        effect_size=outcome.effect_size,
        p_value=outcome.p_value,
        confidence=outcome.confidence,
        critic_verdict=critique.verdict,
        critic_notes=critique.note_text,
        critic_checks=critique.as_dict(),
        limitations="; ".join(outcome.limitations) or None,
        is_demo=hypothesis.is_demo,
    )
    session.add(result)
    await session.flush()

    status = hypothesis_status(outcome.outcome, critique.verdict)
    hypothesis.status = status
    hypothesis.confidence = outcome.confidence
    await session.flush()

    if outcome.outcome == str(ResultOutcome.SUPPORTED):
        report.supported += 1
    elif outcome.outcome == str(ResultOutcome.REJECTED):
        report.rejected += 1
    else:
        report.inconclusive += 1

    await _event(
        session,
        event_type=EventType.EXPERIMENT_COMPLETED,
        message=f"#{experiment.seq:06d} {outcome.summary[:120]}",
        occurred_at=utcnow(),
        ref_type="experiment",
        ref_id=experiment.id,
        is_demo=hypothesis.is_demo,
    )
    await _event(
        session,
        event_type=EventType.CRITIC_RESULT,
        message=f"{critique.verdict}: {critique.note_text[:120]}",
        occurred_at=utcnow(),
        level="WARN" if critique.verdict != "PASS" else "INFO",
        ref_type="experiment",
        ref_id=experiment.id,
        is_demo=hypothesis.is_demo,
    )
    await _event(
        session,
        event_type=(
            EventType.HYPOTHESIS_SUPPORTED
            if status == str(HypothesisStatus.SUPPORTED)
            else EventType.HYPOTHESIS_REJECTED
        ),
        message=f"#{hypothesis.seq} {status.lower()}",
        occurred_at=utcnow(),
        ref_type="hypothesis",
        ref_id=hypothesis.id,
        is_demo=hypothesis.is_demo,
    )

    if trace is not None:
        trace.experiment_id = experiment.id
        await _add_step(
            session,
            trace,
            kind=TraceStepKind.DATASET,
            summary=(
                f"{len(dataset.rows)} token-hours over {len(dataset.tokens)} tokens; "
                f"hash {dataset.hash()[:12]}…"
            ),
            occurred_at=now,
            detail={"excluded": dataset.excluded},
        )
        await _add_step(
            session,
            trace,
            kind=TraceStepKind.EXPERIMENT,
            summary=f"#{experiment.seq:06d} {template.key}",
            occurred_at=now,
            ref_type="experiment",
            ref_id=experiment.id,
        )
        await _add_step(
            session,
            trace,
            kind=TraceStepKind.CRITIC,
            summary=f"{critique.verdict}: {critique.note_text}",
            occurred_at=utcnow(),
            detail=critique.checks,
        )
        await _add_step(
            session,
            trace,
            kind=TraceStepKind.RESULT,
            summary=outcome.summary,
            occurred_at=utcnow(),
            ref_type="experiment",
            ref_id=experiment.id,
        )

    memory_type = "FAILURE" if outcome.outcome == str(ResultOutcome.REJECTED) else "RESULT"
    stored = await store_memory(
        session,
        memory_type=memory_type,
        content=f"{template.question} — {outcome.summary}",
        summary=f"{template.key}: {outcome.outcome.lower()}",
        meta={
            "template": template.key,
            "critic": critique.verdict,
            "metrics": outcome.metrics,
        },
        source="research-pipeline",
        confidence=outcome.confidence,
        ref_type="experiment",
        ref_id=experiment.id,
        is_demo=hypothesis.is_demo,
        commit=False,
    )
    if stored.created:
        report.memories_written += 1
        if trace is not None:
            await _add_step(
                session,
                trace,
                kind=TraceStepKind.MEMORY_UPDATE,
                summary=f"{memory_type.lower()} stored: {stored.memory.summary}",
                occurred_at=utcnow(),
                ref_type="memory",
                ref_id=stored.memory.id,
            )
        await _event(
            session,
            event_type=EventType.MEMORY_UPDATED,
            message=f"{memory_type.lower()} stored for experiment #{experiment.seq:06d}",
            occurred_at=utcnow(),
            ref_type="memory",
            ref_id=stored.memory.id,
            is_demo=hypothesis.is_demo,
        )

    body, content_type = _draft_body(hypothesis, experiment, outcome, critique.verdict)
    session.add(
        ContentDraft(
            content_type=str(content_type),
            body=body,
            status="PENDING",
            source_kind="experiment",
            source_id=experiment.id,
            reviewer_notes=f"generated by {DRAFT_SOURCE}; every number comes from the result row",
            is_demo=hypothesis.is_demo,
        )
    )
    report.drafts_created += 1
    await _event(
        session,
        event_type=EventType.DRAFT_CREATED,
        message=f"{content_type} draft queued for approval",
        occurred_at=utcnow(),
        ref_type="experiment",
        ref_id=experiment.id,
        is_demo=hypothesis.is_demo,
    )

    await _update_pattern(session, hypothesis, outcome, report)

    if trace is not None:
        trace.completed_at = utcnow()
    await session.flush()
    return experiment


async def run_research_cycle(
    session: AsyncSession, *, settings: Settings | None = None, commit: bool = True
) -> ResearchReport:
    settings = settings or get_settings()
    started = utcnow()
    report = ResearchReport()

    await generate_hypotheses(session, settings=settings, report=report)

    pending = (
        await session.scalars(
            select(Hypothesis).where(Hypothesis.status == str(HypothesisStatus.PROPOSED))
        )
    ).all()
    for hypothesis in pending:
        await run_experiment_for(session, hypothesis, settings=settings, report=report)

    report.duration_ms = int((utcnow() - started).total_seconds() * 1000)

    session.add(
        AgentRun(
            agent_name=RESEARCH_RUN_NAME,
            model=None,
            input_summary=f"{len(pending)} proposed hypotheses",
            output_summary=(
                f"{report.experiments_run} experiments: {report.supported} supported, "
                f"{report.rejected} rejected, {report.inconclusive} inconclusive "
                f"(critic version {CRITIC_VERSION})"
            ),
            duration_ms=report.duration_ms,
            status="OK",
            estimated_cost_usd=0.0,
            started_at=started,
            is_demo=True,
        )
    )

    if commit:
        await session.commit()
    return report
