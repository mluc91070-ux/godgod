"""Gate for the model layer: writer, reviewer, budget guard.

Runs against a fake provider, so it costs nothing and proves what matters:
nothing is spent that cannot be measured, nothing is stored that cannot be
checked, and a failed call never looks like a quiet answer.

With ANTHROPIC_API_KEY set this still makes no real call — the fake provider is
injected deliberately. Verifying the live client is a deployment step, not a
gate, and DEPLOYMENT.md says so.
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
    from sqlalchemy.orm import selectinload

    from app.agents import IMPLEMENTED_AGENTS, check_draft, review_draft, write_draft_for_result
    from app.agents.base import run_agent
    from app.core.config import get_settings
    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.models import Agent, AgentRun, Base, ContentDraft, Experiment, ExperimentResult
    from app.providers.base import ProviderNotConfigured
    from app.providers.model import (
        ModelCallFailed,
        ModelProvider,
        ModelResponse,
        NullModelProvider,
        model_for_role,
    )
    from app.providers.source import FixtureObservationSource
    from app.services.budget import BudgetExceeded, require_budget
    from app.services.observation import run_backfill
    from app.services.research import run_research_cycle
    from app.services.seed import seed_demo

    class Fake(ModelProvider):
        name = "fake"
        implemented = True

        def __init__(self, text: str, *, raises: Exception | None = None) -> None:
            self.text = text
            self.raises = raises
            self.calls: list[str] = []

        async def complete(self, *, system, prompt, role, max_tokens=1024, effort="low"):
            self.calls.append(role)
            if self.raises:
                raise self.raises
            return ModelResponse(
                text=self.text,
                model="fake-model",
                input_tokens=100,
                output_tokens=50,
                stop_reason="end_turn",
                cost_usd=0.001,
            )

    failures = 0
    settings = get_settings()

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        await seed_demo(session)
    async with get_sessionmaker()() as session:
        await run_backfill(session, source=FixtureObservationSource())
    async with get_sessionmaker()() as session:
        await run_research_cycle(session)

    # -- the roster tells the truth ---------------------------------------
    async with get_sessionmaker()() as session:
        rows = (await session.scalars(select(Agent))).all()
        failures += not check(
            "only agents that actually run are marked implemented",
            all(row.implemented is (row.name in IMPLEMENTED_AGENTS) for row in rows),
            ", ".join(sorted(IMPLEMENTED_AGENTS)),
        )

    # -- no model name is hard-coded --------------------------------------
    saved = settings.model_writer
    settings.model_writer = None
    try:
        model_for_role(settings, "MODEL_WRITER")
        failures += not check("an unset model role refuses", False)
    except ProviderNotConfigured:
        failures += not check("an unset model role refuses", True)
    settings.model_writer = saved

    try:
        await NullModelProvider().complete(system="s", prompt="p", role="MODEL_WRITER")
        failures += not check("the null provider refuses rather than returning text", False)
    except ProviderNotConfigured:
        failures += not check("the null provider refuses rather than returning text", True)

    # -- the budget guard --------------------------------------------------
    settings.model_price_input_usd_per_mtok = None
    settings.model_price_output_usd_per_mtok = None
    async with get_sessionmaker()() as session:
        try:
            await require_budget(session, settings=settings)
            failures += not check("an unpriced deployment may not spend", False)
        except BudgetExceeded as exc:
            failures += not check(
                "an unpriced deployment may not spend", "MODEL_PRICE" in str(exc)
            )

    settings.model_price_input_usd_per_mtok = 3.0
    settings.model_price_output_usd_per_mtok = 15.0
    settings.llm_daily_budget_usd = 3.0

    async with get_sessionmaker()() as session:
        status = await require_budget(session, settings=settings)
        failures += not check(
            "a priced deployment with budget left may spend",
            status.remaining_usd > 0,
            f"${status.remaining_usd:.2f} left",
        )

    # -- a failed call is recorded, not swallowed --------------------------
    async with get_sessionmaker()() as session:
        outcome = await run_agent(
            session,
            name="writer",
            role="MODEL_WRITER",
            system="s",
            prompt="p",
            input_summary="gate",
            settings=settings,
            provider=Fake("", raises=ModelCallFailed("HTTP 529")),
        )
        await session.commit()
        failures += not check("a failed call returns not-ok", outcome.ok is False)
        run = await session.scalar(select(AgentRun).where(AgentRun.id == outcome.run_id))
        failures += not check(
            "a failed call is recorded as ERROR with no cost",
            run.status == "ERROR" and run.estimated_cost_usd is None,
        )

    # -- the writer refuses an invented number -----------------------------
    async with get_sessionmaker()() as session:
        result = await session.scalar(select(ExperimentResult).limit(1))
        before = len((await session.scalars(select(ContentDraft))).all())
        refused = await write_draft_for_result(
            session,
            result.id,
            settings=settings,
            provider=Fake("i tested 9999 tokens and found nothing."),
        )
        after = len((await session.scalars(select(ContentDraft))).all())
        failures += not check("a draft with an invented number is refused", refused.ok is False)
        failures += not check("a refused draft is not stored", after == before)

        accepted = await write_draft_for_result(
            session,
            result.id,
            settings=settings,
            provider=Fake(f"hypothesis: {result.outcome.lower()}. i can't tell yet."),
        )
        failures += not check(
            "an accurate draft is stored as pending",
            accepted.ok and accepted.draft_id is not None,
            "; ".join(accepted.reasons) or accepted.error or "",
        )

    # -- the reviewer ------------------------------------------------------
    async with get_sessionmaker()() as session:
        draft = await session.scalar(
            select(ContentDraft).where(ContentDraft.source_kind == "experiment_result")
        )
        model = Fake('{"verdict": "APPROVE", "reason": "accurate"}')
        review = await review_draft(session, draft.id, settings=settings, provider=model)
        failures += not check(
            "an accurate draft is approved by the reviewer",
            review.approved,
            "; ".join(review.reasons),
        )
        failures += not check(
            "an approval is a verdict, not a publish",
            draft.status == "PENDING" and draft.reviewer_verdict == "APPROVE",
        )

    async with get_sessionmaker()() as session:
        result = await session.scalar(select(ExperimentResult).limit(1))
        bad = ContentDraft(
            content_type="RESULT",
            body="LFG this proves it, 9999 tokens.",
            status="PENDING",
            source_kind="experiment_result",
            source_id=result.id,
            is_demo=True,
        )
        session.add(bad)
        await session.flush()
        model = Fake('{"verdict": "APPROVE", "reason": "fine"}')
        review = await review_draft(session, bad.id, settings=settings, provider=model)
        failures += not check(
            "a model approval cannot override a deterministic failure",
            review.verdict == "REJECT",
        )
        failures += not check(
            "no model was paid to read a draft already refused", model.calls == []
        )

    # -- the checks themselves ---------------------------------------------
    failures += not check(
        "an ungrounded number fails the check",
        check_draft("i saw 91 tokens.", {"n_exposed": 72}).ok is False,
    )
    failures += not check(
        "certainty about an inconclusive result fails the check",
        check_draft("this proves it.", {}, outcome="INCONCLUSIVE").ok is False,
    )
    failures += not check(
        "an accurate lowercase draft passes",
        check_draft("hypothesis 41: 72 token-hours. i can't tell yet.",
                    {"hypothesis_number": 41, "n_exposed": 72}).ok,
    )

    # -- every draft still points at something checkable -------------------
    async with get_sessionmaker()() as session:
        drafts = (await session.scalars(select(ContentDraft))).all()
        failures += not check(
            "no draft is published",
            all(draft.status != "PUBLISHED" for draft in drafts),
        )
        experiments = (
            await session.scalars(
                select(Experiment).options(selectinload(Experiment.results))
            )
        ).all()
        failures += not check("experiments exist to write about", bool(experiments))

    await dispose_engine()
    print()
    print("agent-layer gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
