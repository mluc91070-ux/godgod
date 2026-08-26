"""PHASE 4-6 gate: hypothesis, experiment, critic.

Replays the synthetic series, runs one research cycle over it, and checks the
properties that make the output research rather than decoration: falsification
rules applied as written, no look-ahead, no model in the loop, no unsupported
claim, and every experiment re-runnable from what was recorded.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> int:
    from sqlalchemy import select

    from app.core.enums import CriticVerdict, HypothesisStatus, ResultOutcome
    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.models import (
        AgentRun,
        Base,
        ContentDraft,
        Experiment,
        ExperimentResult,
        Hypothesis,
        Memory,
        ResearchTrace,
        TraceStep,
    )
    from app.providers.source import FixtureObservationSource
    from app.services.observation import run_backfill
    from app.services.research import (
        CHECK_NAMES,
        MIN_CELL,
        RESEARCH_RUN_NAME,
        TEMPLATES,
        build_dataset,
        evaluate,
        run_research_cycle,
    )
    from app.services.research.critic import hypothesis_status
    from app.services.research.templates import TEMPLATES_BY_KEY

    failures = 0

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        await run_backfill(session, source=FixtureObservationSource())
        report = await run_research_cycle(session)

        failures += not check(
            "cycle produced hypotheses",
            report.hypotheses_created > 0,
            f"{report.hypotheses_created} created",
        )
        failures += not check(
            "every hypothesis was tested",
            report.experiments_run == report.hypotheses_created,
            f"{report.experiments_run} experiments",
        )
        failures += not check(
            "no model in the loop",
            report.as_dict()["llm_calls"] == 0,
        )
        failures += not check(
            "skips are named, not silent",
            all(reason and count > 0 for reason, count in report.skipped.items()),
            str(report.skipped) or "nothing skipped",
        )

        # -- falsification is applied as written, in the right direction ----
        directional = 0
        for template in TEMPLATES:
            dataset = await build_dataset(session, template)
            outcome = evaluate(dataset, template)
            signed = outcome.metrics.get("signed_difference_pp")
            raw = outcome.metrics.get("difference_pp")
            if signed is None or raw is None:
                continue
            directional += 1
            expected = round(raw * template.expected_direction, 2)
            if abs(signed - expected) > 0.01:
                failures += not check(f"{template.key}: direction applied", False)
        failures += not check(
            "every template's effect is read in its declared direction",
            directional > 0,
            f"{directional} templates measured",
        )

        # -- no look-ahead in any dataset -----------------------------------
        violations = 0
        for template in TEMPLATES:
            dataset = await build_dataset(session, template)
            violations += sum(1 for row in dataset.rows if row.outcome_at <= row.exposure_at)
        failures += not check("no outcome read at or before its exposure", violations == 0)

        # -- a small sample never becomes a verdict -------------------------
        small = TEMPLATES_BY_KEY[next(iter(TEMPLATES_BY_KEY))]
        thin = await build_dataset(session, small)
        thin.rows = thin.rows[:4]
        thin_outcome = evaluate(thin, small)
        failures += not check(
            "a sample below the minimum is inconclusive, not rejected",
            thin_outcome.outcome == str(ResultOutcome.INCONCLUSIVE),
            f"minimum is {MIN_CELL} per group",
        )

        # -- stored rows ----------------------------------------------------
        experiments = (await session.scalars(select(Experiment))).all()
        failures += not check(
            "every experiment records dataset version and hash",
            all(e.dataset_version and len(e.dataset_hash or "") == 64 for e in experiments),
        )
        failures += not check(
            "every experiment records its parameters",
            all(e.parameters for e in experiments),
        )

        results = (await session.scalars(select(ExperimentResult))).all()
        valid_verdicts = {str(item) for item in CriticVerdict}
        failures += not check(
            "every result carries a critic verdict and its checks",
            bool(results)
            and all(r.critic_verdict in valid_verdicts and r.critic_checks for r in results),
        )
        failures += not check(
            "the critic ran every declared check",
            all(set(CHECK_NAMES) <= set(r.critic_checks or {}) for r in results),
            f"{len(CHECK_NAMES)} checks",
        )
        failures += not check(
            "a supported result is significant",
            all(
                (r.p_value is not None and r.p_value <= 0.05)
                for r in results
                if r.outcome == str(ResultOutcome.SUPPORTED)
            ),
        )

        rows = (
            await session.execute(
                select(Hypothesis.status, ExperimentResult.critic_verdict)
                .join(Experiment, Experiment.hypothesis_id == Hypothesis.id)
                .join(ExperimentResult, ExperimentResult.experiment_id == Experiment.id)
            )
        ).all()
        failures += not check(
            "nothing is SUPPORTED without a passing critic",
            all(
                verdict == str(CriticVerdict.PASS)
                for status, verdict in rows
                if status == str(HypothesisStatus.SUPPORTED)
            ),
        )
        failures += not check(
            "the gate itself rejects a supported result with a failing critic",
            hypothesis_status(str(ResultOutcome.SUPPORTED), str(CriticVerdict.FAIL))
            == str(HypothesisStatus.INCONCLUSIVE),
        )

        hypotheses = (await session.scalars(select(Hypothesis))).all()
        tested = [h for h in hypotheses if h.origin_observation_id]
        failures += not check(
            "memory was consulted before each hypothesis",
            bool(tested) and all("memory_consulted" in (h.variables or {}) for h in tested),
        )

        traces = (await session.scalars(select(ResearchTrace))).all()
        completed = [t for t in traces if t.completed_at]
        steps = (await session.scalars(select(TraceStep))).all()
        kinds = {step.kind for step in steps}
        failures += not check(
            "each tested hypothesis has a completed trace",
            len(completed) >= report.experiments_run,
            f"{len(completed)} traces",
        )
        failures += not check(
            "the trace covers observation through result",
            {"OBSERVATION", "ANOMALY", "HYPOTHESIS", "DATASET", "EXPERIMENT", "CRITIC", "RESULT"}
            <= kinds,
            ", ".join(sorted(kinds)),
        )

        drafts = (
            await session.scalars(
                select(ContentDraft).where(ContentDraft.source_kind == "experiment")
            )
        ).all()
        failures += not check(
            "drafts stay pending and unapproved",
            bool(drafts) and all(d.status == "PENDING" and not d.approved_at for d in drafts),
            f"{len(drafts)} drafts",
        )
        failures += not check(
            "every draft points at the result it came from",
            all(d.source_id for d in drafts),
        )

        memories = (
            await session.scalars(select(Memory).where(Memory.ref_type == "experiment"))
        ).all()
        failures += not check(
            "what was learned was written to memory",
            bool(memories),
            f"{len(memories)} memories",
        )

        runs = (
            await session.scalars(
                select(AgentRun).where(AgentRun.agent_name == RESEARCH_RUN_NAME)
            )
        ).all()
        failures += not check(
            "runs recorded with no model and zero cost",
            bool(runs) and all(r.model is None and r.estimated_cost_usd == 0.0 for r in runs),
        )

        second = await run_research_cycle(session)
        failures += not check(
            "a second cycle asks nothing already asked",
            second.hypotheses_created == 0,
        )

    await dispose_engine()
    print()
    print("PHASE 4-6 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
