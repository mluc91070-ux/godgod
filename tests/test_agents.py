"""The model-backed agents: writer, reviewer, budget guard, output checks.

No real model is called anywhere in this file. What is tested is the machinery
around the call — the part that decides whether to spend, what to believe, and
what to store — because that is the part that has to hold when the model is
wrong, expensive, or unavailable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.agents.base import run_agent
from app.agents.guards import check_draft, numbers_in, ungrounded_numbers
from app.agents.reviewer import REVIEWER_VERSION, parse_verdict, review_draft
from app.agents.writer import WRITER_SOURCE, build_prompt, facts_for, write_draft_for_result
from app.core.untrusted import SYSTEM_RULE
from app.models import AgentRun, ContentDraft, Experiment, ExperimentResult, SystemEvent
from app.providers.base import ProviderNotConfigured
from app.providers.model import (
    MODEL_ROLES,
    ModelCallFailed,
    ModelProvider,
    ModelResponse,
    NullModelProvider,
    model_for_role,
    price,
)
from app.providers.source import FixtureObservationSource
from app.services.budget import BudgetExceeded, get_budget_status, require_budget
from app.services.observation import run_backfill
from app.services.research import run_research_cycle


class FakeModel(ModelProvider):
    """Answers whatever the test tells it to, and records what it was asked."""

    name = "fake"
    implemented = True

    def __init__(
        self,
        text: str = "hypothesis #000041 was inconclusive.",
        *,
        raises: Exception | None = None,
        stop_reason: str = "end_turn",
        cost: float | None = 0.001,
    ) -> None:
        self.text = text
        self.raises = raises
        self.stop_reason = stop_reason
        self.cost = cost
        self.calls: list[dict] = []

    async def complete(self, *, system, prompt, role, max_tokens=1024, effort="low"):
        self.calls.append(
            {"system": system, "prompt": prompt, "role": role, "max_tokens": max_tokens}
        )
        if self.raises:
            raise self.raises
        return ModelResponse(
            text=self.text,
            model="fake-model",
            input_tokens=100,
            output_tokens=50,
            stop_reason=self.stop_reason,
            cost_usd=self.cost,
        )


@pytest_asyncio.fixture
async def priced(settings):
    """Prices configured, so the budget guard has something to measure."""
    settings.model_price_input_usd_per_mtok = 3.0
    settings.model_price_output_usd_per_mtok = 15.0
    settings.llm_daily_budget_usd = 3.0
    return settings


@pytest_asyncio.fixture
async def researched(session, priced):
    await run_backfill(session, source=FixtureObservationSource(), settings=priced)
    await run_research_cycle(session, settings=priced)
    result = await session.scalar(select(ExperimentResult).limit(1))
    return result


# -- pricing and roles ----------------------------------------------------


def test_price_is_none_when_unpriced(settings) -> None:
    settings.model_price_input_usd_per_mtok = None
    assert price(settings, 1000, 1000) is None


def test_price_is_computed_per_million_tokens(priced) -> None:
    # 1M in at $3 plus 1M out at $15.
    assert price(priced, 1_000_000, 1_000_000) == pytest.approx(18.0)
    assert price(priced, 1000, 500) == pytest.approx(0.0105, abs=1e-6)


def test_a_model_role_must_be_configured_not_hard_coded(settings) -> None:
    settings.model_writer = None
    with pytest.raises(ProviderNotConfigured, match="MODEL_WRITER"):
        model_for_role(settings, "MODEL_WRITER")

    settings.model_writer = "configured-model-id"
    assert model_for_role(settings, "MODEL_WRITER") == "configured-model-id"


def test_an_unknown_role_is_a_programming_error(settings) -> None:
    with pytest.raises(ValueError, match="unknown model role"):
        model_for_role(settings, "MODEL_VIBES")


def test_the_roles_are_the_four_documented_ones() -> None:
    assert MODEL_ROLES == ("MODEL_FAST", "MODEL_REASONING", "MODEL_WRITER", "MODEL_CRITIC")


async def test_the_null_provider_refuses_rather_than_returning_nothing() -> None:
    with pytest.raises(ProviderNotConfigured, match="ANTHROPIC_API_KEY"):
        await NullModelProvider().complete(system="s", prompt="p", role="MODEL_WRITER")


# -- the budget guard -----------------------------------------------------


async def test_an_unpriced_deployment_may_not_spend(session, settings) -> None:
    settings.model_price_input_usd_per_mtok = None
    with pytest.raises(BudgetExceeded, match="MODEL_PRICE"):
        await require_budget(session, settings=settings)


async def test_budget_allows_a_call_when_nothing_has_been_spent(session, priced) -> None:
    status = await require_budget(session, settings=priced)
    assert status.spent_today_usd == 0.0
    assert status.remaining_usd == priced.llm_daily_budget_usd


async def test_budget_refuses_once_the_day_is_spent(session, priced) -> None:
    session.add(
        AgentRun(
            agent_name="writer",
            model="fake-model",
            status="OK",
            estimated_cost_usd=priced.llm_daily_budget_usd,
            started_at=datetime.now(UTC),
            is_demo=True,
        )
    )
    await session.commit()
    with pytest.raises(BudgetExceeded, match="budget is spent"):
        await require_budget(session, settings=priced)


async def test_budget_refuses_when_the_day_holds_an_unmeasured_run(session, priced) -> None:
    """Spend that is known to be incomplete is not a number to spend against."""
    session.add(
        AgentRun(
            agent_name="writer",
            model="fake-model",
            status="OK",
            estimated_cost_usd=None,
            started_at=datetime.now(UTC),
            is_demo=True,
        )
    )
    await session.commit()
    with pytest.raises(BudgetExceeded, match="floor"):
        await require_budget(session, settings=priced)


async def test_yesterdays_spend_does_not_count_against_today(session, priced) -> None:
    session.add(
        AgentRun(
            agent_name="writer",
            model="fake-model",
            status="OK",
            estimated_cost_usd=99.0,
            started_at=datetime.now(UTC) - timedelta(days=1, hours=1),
            is_demo=True,
        )
    )
    await session.commit()
    status = await get_budget_status(session, settings=priced)
    assert status.spent_today_usd == 0.0


# -- run_agent ------------------------------------------------------------


async def test_a_successful_run_is_recorded_with_tokens_and_cost(session, priced) -> None:
    model = FakeModel(text="ok")
    outcome = await run_agent(
        session,
        name="writer",
        role="MODEL_WRITER",
        system="s",
        prompt="p",
        input_summary="test",
        settings=priced,
        provider=model,
    )
    assert outcome.ok
    run = await session.scalar(select(AgentRun).where(AgentRun.agent_name == "writer"))
    assert run.status == "OK"
    assert run.model == "fake-model"
    assert (run.input_tokens, run.output_tokens) == (100, 50)
    assert run.estimated_cost_usd == 0.001
    assert run.duration_ms is not None


async def test_a_failed_call_is_recorded_and_logged_not_swallowed(session, priced) -> None:
    model = FakeModel(raises=ModelCallFailed("HTTP 529: overloaded"))
    outcome = await run_agent(
        session,
        name="writer",
        role="MODEL_WRITER",
        system="s",
        prompt="p",
        input_summary="test",
        settings=priced,
        provider=model,
    )
    assert outcome.ok is False
    assert "overloaded" in outcome.error

    run = await session.scalar(select(AgentRun).where(AgentRun.agent_name == "writer"))
    assert run.status == "ERROR"
    assert run.estimated_cost_usd is None

    event = await session.scalar(
        select(SystemEvent).where(SystemEvent.ref_id == run.id)
    )
    assert event.level == "ERROR"


async def test_a_truncated_answer_is_a_failure_not_a_result(session, priced) -> None:
    model = FakeModel(text="hypothesis #000041 was", stop_reason="max_tokens")
    outcome = await run_agent(
        session,
        name="writer",
        role="MODEL_WRITER",
        system="s",
        prompt="p",
        input_summary="test",
        settings=priced,
        provider=model,
    )
    assert outcome.ok is False
    assert "incomplete" in outcome.error
    assert outcome.text is None


async def test_a_refused_budget_records_a_skipped_run_and_makes_no_call(
    session, settings
) -> None:
    settings.model_price_input_usd_per_mtok = None
    model = FakeModel()
    outcome = await run_agent(
        session,
        name="writer",
        role="MODEL_WRITER",
        system="s",
        prompt="p",
        input_summary="test",
        settings=settings,
        provider=model,
    )
    assert outcome.ok is False
    assert model.calls == []
    run = await session.scalar(select(AgentRun).where(AgentRun.agent_name == "writer"))
    assert run.status == "SKIPPED"


# -- the output checks ----------------------------------------------------


def test_numbers_are_extracted_with_separators_normalised() -> None:
    assert numbers_in("1,234 and 5.6 and -7") == ["1234", "5.6", "-7"]


def test_a_number_absent_from_the_facts_is_ungrounded() -> None:
    facts = {"n_exposed": 72, "p_value": 0.31}
    assert ungrounded_numbers("72 rows, p=0.31", facts) == []
    assert ungrounded_numbers("104 rows", facts) == ["104"]


def test_a_rate_may_be_written_as_a_percentage() -> None:
    facts = {"rate_exposed": 0.42}
    assert ungrounded_numbers("42% survived", facts) == []


def test_a_draft_stating_an_invented_number_is_refused() -> None:
    check = check_draft("i found 91 tokens that behaved this way.", {"n_exposed": 72})
    assert check.ok is False
    assert any("91" in reason for reason in check.reasons)


@pytest.mark.parametrize(
    "text",
    [
        "this one is bullish.",
        "you should buy this before it moves.",
        "it is going to pump.",
        "read more at https://example.com",
        "as an ai, i cannot be sure.",
        "guaranteed 100x from here.",
    ],
)
def test_claims_about_price_are_refused(text: str) -> None:
    """What is banned is the claim, not the register."""
    assert check_draft(text, {}).ok is False


@pytest.mark.parametrize(
    "text",
    [
        "lfg, i was wrong again.",
        "gm. killed one of my own hypotheses today.",
        "degen hours. no signal.",
        "ngmi, apparently. inconclusive.",
        "this one's a shrug. ape at your own peril, i have no idea.",
    ],
)
def test_slang_alone_is_allowed(text: str) -> None:
    """The register is crypto-native on purpose. Only the claims are policed —
    a post is allowed to sound like the timeline while refusing to lie to it."""
    check = check_draft(text, {})
    assert check.ok, check.reasons


def test_certainty_about_an_inconclusive_result_is_refused() -> None:
    check = check_draft("this proves the effect is real.", {}, outcome="INCONCLUSIVE")
    assert any("certainty" in reason for reason in check.reasons)


def test_an_overlong_draft_is_refused() -> None:
    check = check_draft("a" * 300, {})
    assert any("over the 280" in reason for reason in check.reasons)


def test_an_accurate_lowercase_draft_passes() -> None:
    facts = {"hypothesis_number": 41, "n_exposed": 72, "p_value": 0.31}
    check = check_draft(
        "hypothesis 41: 72 token-hours, p 0.31. i can't tell yet.", facts, outcome="INCONCLUSIVE"
    )
    assert check.ok, check.reasons


# -- the writer -----------------------------------------------------------


async def test_the_writer_stores_a_draft_that_survives_the_checks(
    session, priced, researched
) -> None:
    result = researched
    facts = {"outcome": result.outcome}
    text = f"hypothesis: {result.outcome.lower()}. i can't tell yet."
    outcome = await write_draft_for_result(
        session, result.id, settings=priced, provider=FakeModel(text=text), commit=False
    )
    assert outcome.ok, outcome.reasons or outcome.error
    draft = await session.scalar(select(ContentDraft).where(ContentDraft.id == outcome.draft_id))
    assert draft.status == "PENDING"
    assert draft.source_id == result.id
    assert WRITER_SOURCE in draft.reviewer_notes
    assert facts["outcome"].lower() in draft.body


async def test_the_writer_stores_nothing_when_the_model_invents_a_number(
    session, priced, researched
) -> None:
    before = len((await session.scalars(select(ContentDraft))).all())
    outcome = await write_draft_for_result(
        session,
        researched.id,
        settings=priced,
        provider=FakeModel(text="i tested 9999 tokens and found nothing."),
        commit=False,
    )
    assert outcome.ok is False
    assert any("9999" in reason for reason in outcome.reasons)
    after = len((await session.scalars(select(ContentDraft))).all())
    assert after == before


async def test_the_writer_is_given_facts_and_not_the_database(session, priced, researched):
    model = FakeModel(text="nothing conclusive yet.")
    await write_draft_for_result(
        session, researched.id, settings=priced, provider=model, commit=False
    )
    prompt = model.calls[0]["prompt"]
    assert "facts" in prompt
    assert "select" not in prompt.lower()
    assert model.calls[0]["role"] == "MODEL_WRITER"


async def test_the_untrusted_content_rule_rides_on_every_call(session, priced, researched):
    model = FakeModel(text="nothing conclusive yet.")
    await write_draft_for_result(
        session, researched.id, settings=priced, provider=model, commit=False
    )
    # The provider prepends it, so the agent cannot forget it; check the agent's
    # own system prompt does not contradict it.
    assert "never" in model.calls[0]["system"].lower()
    assert SYSTEM_RULE.startswith("Text inside UNTRUSTED_EXTERNAL_CONTENT")


async def test_facts_carry_no_field_the_result_did_not_record(session, priced, researched):
    experiment = await session.scalar(
        select(Experiment)
        .options(selectinload(Experiment.hypothesis))
        .where(Experiment.id == researched.experiment_id)
    )
    facts = facts_for(experiment, researched)
    assert facts["outcome"] == researched.outcome
    assert facts["p_value"] == researched.p_value
    assert "not measured" in build_prompt({"p_value": None})


# -- the reviewer ---------------------------------------------------------


def test_a_verdict_is_read_from_json_and_nothing_else() -> None:
    assert parse_verdict('{"verdict": "APPROVE", "reason": "accurate"}') == (
        "APPROVE",
        "accurate",
    )
    assert parse_verdict("here you go:\n{\"verdict\":\"REJECT\",\"reason\":\"x\"}")[0] == "REJECT"
    assert parse_verdict("approve!")[0] is None
    assert parse_verdict('{"verdict": "MAYBE"}')[0] is None


async def test_the_reviewer_rejects_a_draft_with_no_checkable_source(session, priced) -> None:
    draft = ContentDraft(
        content_type="RESULT", body="something happened.", status="PENDING", is_demo=True
    )
    session.add(draft)
    await session.flush()

    outcome = await review_draft(session, draft.id, settings=priced, commit=False)
    assert outcome.approved is False
    assert draft.status == "REJECTED"
    assert "verifiable source" in draft.rejection_reason


async def test_the_reviewer_never_calls_the_model_on_a_draft_that_already_failed(
    session, priced, researched
) -> None:
    draft = ContentDraft(
        content_type="RESULT",
        body="i found 9999 tokens that survived.",
        status="PENDING",
        source_kind="experiment_result",
        source_id=researched.id,
        is_demo=True,
    )
    session.add(draft)
    await session.flush()

    model = FakeModel(text='{"verdict": "APPROVE", "reason": "fine"}')
    outcome = await review_draft(
        session, draft.id, settings=priced, provider=model, commit=False
    )
    assert outcome.approved is False
    assert model.calls == [], "no reason to pay for a reading of a draft already refused"


async def test_a_model_approval_cannot_override_a_deterministic_failure(
    session, priced, researched
) -> None:
    draft = ContentDraft(
        content_type="RESULT",
        body="LFG this proves it, 9999 tokens.",
        status="PENDING",
        source_kind="experiment_result",
        source_id=researched.id,
        is_demo=True,
    )
    session.add(draft)
    await session.flush()

    outcome = await review_draft(
        session,
        draft.id,
        settings=priced,
        provider=FakeModel(text='{"verdict": "APPROVE", "reason": "looks good"}'),
        commit=False,
    )
    assert outcome.verdict == "REJECT"
    assert outcome.model_verdict is None


async def test_a_model_rejection_stands_over_passing_checks(session, priced, researched) -> None:
    draft = ContentDraft(
        content_type="RESULT",
        body=f"hypothesis: {researched.outcome.lower()}. i can't tell yet.",
        status="PENDING",
        source_kind="experiment_result",
        source_id=researched.id,
        is_demo=True,
    )
    session.add(draft)
    await session.flush()

    outcome = await review_draft(
        session,
        draft.id,
        settings=priced,
        provider=FakeModel(text='{"verdict": "REJECT", "reason": "implies a finding"}'),
        commit=False,
    )
    assert outcome.verdict == "REJECT"
    assert outcome.model_verdict == "REJECT"
    assert any("implies a finding" in reason for reason in outcome.reasons)


async def test_a_review_without_a_model_says_so(session, settings, researched) -> None:
    """Deterministic-only review must not read like a full one."""
    settings.model_price_input_usd_per_mtok = None
    draft = ContentDraft(
        content_type="RESULT",
        body=f"hypothesis: {researched.outcome.lower()}. i can't tell yet.",
        status="PENDING",
        source_kind="experiment_result",
        source_id=researched.id,
        is_demo=True,
    )
    session.add(draft)
    await session.flush()

    outcome = await review_draft(session, draft.id, settings=settings, commit=False)
    assert outcome.model_verdict is None
    assert "no model reviewed this draft" in draft.reviewer_notes
    assert REVIEWER_VERSION in draft.reviewer_notes


async def test_an_approval_is_a_verdict_not_a_publish(session, priced, researched) -> None:
    draft = ContentDraft(
        content_type="RESULT",
        body=f"hypothesis: {researched.outcome.lower()}. i can't tell yet.",
        status="PENDING",
        source_kind="experiment_result",
        source_id=researched.id,
        is_demo=True,
    )
    session.add(draft)
    await session.flush()

    outcome = await review_draft(
        session,
        draft.id,
        settings=priced,
        provider=FakeModel(text='{"verdict": "APPROVE", "reason": "accurate"}'),
        commit=False,
    )
    assert outcome.approved
    assert draft.reviewer_verdict == "APPROVE"
    assert draft.status == "PENDING", "the operator approves; the reviewer only advises"


# -- the endpoints --------------------------------------------------------


async def test_budget_endpoint_reports_an_unpriced_deployment(client) -> None:
    body = (await client.get("/api/budget")).json()
    assert body["priced"] is False
    assert body["spent_today_usd"] == 0.0


async def test_agent_endpoints_require_the_operator_token(client) -> None:
    for path in ("/api/admin/agents/writer/run", "/api/admin/agents/reviewer/run"):
        response = await client.post(path, params={"result_id": "x", "draft_id": "x"})
        assert response.status_code in (401, 403)


async def test_the_writer_endpoint_reports_a_refusal_rather_than_failing(
    client, admin_headers
) -> None:
    results = (await client.get("/api/results")).json()["items"]
    response = await client.post(
        "/api/admin/agents/writer/run",
        params={"result_id": results[0]["id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "MODEL_PRICE" in (body["error"] or "")


async def test_the_writer_endpoint_404s_on_an_unknown_result(client, admin_headers) -> None:
    response = await client.post(
        "/api/admin/agents/writer/run",
        params={"result_id": "does-not-exist"},
        headers=admin_headers,
    )
    assert response.status_code == 404


# -- the voice ------------------------------------------------------------


def test_the_same_result_always_phrases_itself_the_same_way() -> None:
    """Rotating phrasing at random would mean the account says two different
    things about identical data. Small, but exactly the kind of lie this
    project does not get to tell."""
    from app.services.research.voice import inconclusive

    args = ("041", 8.4)
    kwargs = {"n_exposed": 72, "small_sample": False, "key": "experiment-abc"}
    assert inconclusive(*args, **kwargs) == inconclusive(*args, **kwargs)


def test_different_results_do_not_all_sound_identical() -> None:
    from app.services.research.voice import inconclusive

    posts = {
        inconclusive("041", 8.4, n_exposed=72, small_sample=False, key=f"exp-{i}")
        for i in range(12)
    }
    assert len(posts) > 3, "twelve results should not produce one sentence"


@pytest.mark.parametrize("outcome", ["REJECTED", "INCONCLUSIVE", "SUPPORTED"])
def test_every_voice_variant_survives_its_own_checks(outcome: str) -> None:
    """The voice is not allowed to write something the guards would refuse."""
    from app.services.research.voice import inconclusive, rejected, supported

    facts = {"hypothesis_number": 41, "difference_pp": 8.4, "n_exposed": 72, "p_value": 0.031}
    for index in range(20):
        key = f"exp-{index}"
        if outcome == "REJECTED":
            text = rejected("041", 8.4, "the effect points the other way", key)
        elif outcome == "SUPPORTED":
            text = supported("041", 8.4, 0.031, key)
        else:
            text = inconclusive("041", 8.4, n_exposed=72, small_sample=False, key=key)

        check = check_draft(text, facts, outcome=outcome)
        assert check.ok, f"{key}: {check.reasons}\n{text}"
        assert len(text) <= 280, f"{key} is {len(text)} characters"


def test_the_writer_prompt_forbids_claims_while_allowing_register() -> None:
    from app.services.research.voice import WRITER_SYSTEM

    lowered = WRITER_SYSTEM.lower()
    assert "not in the facts" in lowered, "the number rule must be stated"
    assert "where a price is going" in lowered
    assert "crypto-native" in lowered, "the register is deliberate, not an accident"


def test_a_rate_may_be_written_to_two_decimals() -> None:
    """The regression this exists for: the writer said 91.18% for a rate of
    0.911764 — the truth, stated precisely — and the guard called it invented.
    The check is for numbers that are not in the data, not for precision."""
    facts = {"rate_control": 0.9117647058823529, "rate_exposed": 1.0}
    for written in ("91%", "91.2%", "91.18%"):
        assert ungrounded_numbers(f"retention {written} vs 100%", facts) == [], written


def test_a_genuinely_invented_number_is_still_caught() -> None:
    facts = {"rate_control": 0.9117647058823529}
    assert ungrounded_numbers("retention 87.4%", facts) == ["87.4"]
