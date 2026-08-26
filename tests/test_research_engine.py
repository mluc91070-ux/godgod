"""PHASE 4-6: hypothesis, experiment, critic.

These tests check the parts a demo cannot check for itself: that the statistics
are right, that a falsification rule written in advance is applied *as written*
(including its direction), and that a sample too small to settle a question is
not dressed up as a verdict.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import CriticVerdict, HypothesisStatus, ResultOutcome
from app.services.research.critic import CHECK_NAMES, hypothesis_status, review
from app.services.research.dataset import Dataset, DatasetRow, stratum_for
from app.services.research.experiments import MIN_CELL, evaluate
from app.services.research.stats import cohens_h, normal_cdf, two_proportion_test
from app.services.research.templates import TEMPLATES, TEMPLATES_BY_KEY

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def make_rows(
    *, exposed_n: int, exposed_hits: int, control_n: int, control_hits: int, stratum: str = "mid"
) -> list[DatasetRow]:
    rows: list[DatasetRow] = []
    for index in range(exposed_n):
        rows.append(
            DatasetRow(
                token_address=f"exposed-{index % 12}",
                symbol="EXP",
                exposure_at=BASE + timedelta(hours=index),
                outcome_at=BASE + timedelta(hours=index + 6),
                exposed=True,
                outcome=index < exposed_hits,
                stratum=stratum,
                age_hours=float(index),
            )
        )
    for index in range(control_n):
        rows.append(
            DatasetRow(
                token_address=f"control-{index % 12}",
                symbol="CTL",
                exposure_at=BASE + timedelta(hours=index),
                outcome_at=BASE + timedelta(hours=index + 6),
                exposed=False,
                outcome=index < control_hits,
                stratum=stratum,
                age_hours=float(index),
            )
        )
    return rows


def make_dataset(template_key: str = "volume-spike-survival", **kwargs) -> Dataset:
    rows = make_rows(**kwargs)
    return Dataset(
        template_key=template_key,
        rows=rows,
        period_start=min(row.exposure_at for row in rows),
        period_end=max(row.outcome_at for row in rows),
    )


# -- statistics -----------------------------------------------------------


def test_normal_cdf_matches_known_values() -> None:
    assert normal_cdf(0.0) == pytest.approx(0.5, abs=1e-9)
    assert normal_cdf(1.96) == pytest.approx(0.975, abs=1e-3)
    assert normal_cdf(-1.96) == pytest.approx(0.025, abs=1e-3)


def test_two_proportion_test_on_a_textbook_case() -> None:
    # 60/100 vs 40/100 is the standard 20-point difference, z ~ 2.83.
    test = two_proportion_test(60, 100, 40, 100)
    assert test.difference_pp == pytest.approx(20.0)
    assert test.z == pytest.approx(2.83, abs=0.02)
    assert test.p_value is not None and test.p_value < 0.01


def test_identical_rates_are_not_significant() -> None:
    test = two_proportion_test(50, 100, 50, 100)
    assert test.difference == pytest.approx(0.0)
    assert test.p_value == pytest.approx(1.0, abs=1e-6)


def test_empty_group_yields_no_p_value_rather_than_a_guess() -> None:
    test = two_proportion_test(0, 0, 5, 10)
    assert test.p_value is None
    assert test.z is None


def test_cohens_h_is_zero_for_equal_rates_and_grows_with_distance() -> None:
    assert cohens_h(0.5, 0.5) == pytest.approx(0.0, abs=1e-9)
    assert abs(cohens_h(0.8, 0.5)) > abs(cohens_h(0.6, 0.5))


def test_stratum_boundaries_are_closed_below_and_open_above() -> None:
    assert stratum_for(None) == "unknown"
    assert stratum_for(-1.0) == "unknown"
    assert stratum_for(1_000.0) != stratum_for(1_000_000.0)


# -- templates ------------------------------------------------------------


def test_every_template_declares_a_direction_and_a_threshold() -> None:
    for template in TEMPLATES:
        assert template.expected_direction in (1, -1), template.key
        assert template.min_effect_pp > 0, template.key
        assert template.falsification_condition.strip(), template.key
        assert template.horizon_hours > 0, template.key


def test_template_keys_are_unique() -> None:
    assert len(TEMPLATES_BY_KEY) == len(TEMPLATES)


# -- the experiment engine ------------------------------------------------


def test_large_effect_in_the_predicted_direction_is_supported() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=200, exposed_hits=140, control_n=200, control_hits=80)
    outcome = evaluate(dataset, template)
    assert outcome.outcome == str(ResultOutcome.SUPPORTED)
    assert outcome.p_value is not None and outcome.p_value < 0.05
    assert outcome.metrics["signed_difference_pp"] > 0


def test_an_effect_pointing_the_wrong_way_is_rejected_not_confirmed() -> None:
    """The defect this test exists for: a hypothesis predicting a *decrease*
    must not be confirmed by a large increase."""
    template = TEMPLATES_BY_KEY["withdrawal-death"]
    assert template.expected_direction == -1
    dataset = make_dataset(
        template_key=template.key,
        exposed_n=200,
        exposed_hits=160,
        control_n=200,
        control_hits=60,
    )
    outcome = evaluate(dataset, template)
    assert outcome.outcome == str(ResultOutcome.REJECTED)
    assert outcome.metrics["difference_pp"] > 0
    assert outcome.metrics["signed_difference_pp"] < 0
    assert "opposite way" in outcome.summary


def test_effect_below_the_declared_threshold_is_rejected() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=400, exposed_hits=204, control_n=400, control_hits=200)
    outcome = evaluate(dataset, template)
    assert outcome.outcome == str(ResultOutcome.REJECTED)
    assert outcome.metrics["falsification_condition_met"] is True


def test_a_small_sample_is_inconclusive_not_rejected() -> None:
    """A group of one row cannot falsify anything. Saying REJECTED there would
    dress noise up as a verdict."""
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=1, exposed_hits=0, control_n=60, control_hits=30)
    outcome = evaluate(dataset, template)
    assert outcome.outcome == str(ResultOutcome.INCONCLUSIVE)
    assert outcome.metrics["sample_too_small_to_judge"] is True
    assert outcome.metrics["falsification_condition_met"] in (True, False)
    assert str(MIN_CELL) in outcome.summary


def test_empty_dataset_says_nothing_was_tested() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    outcome = evaluate(Dataset(template_key=template.key), template)
    assert outcome.outcome == str(ResultOutcome.INCONCLUSIVE)
    assert outcome.effect_size is None
    assert outcome.p_value is None
    assert outcome.confidence == 0.0


def test_one_empty_group_is_reported_as_such() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=0, exposed_hits=0, control_n=50, control_hits=25)
    outcome = evaluate(dataset, template)
    assert outcome.outcome == str(ResultOutcome.INCONCLUSIVE)
    assert "empty" in outcome.summary


def test_a_sign_reversal_across_strata_falsifies() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    rows = make_rows(
        exposed_n=80, exposed_hits=64, control_n=80, control_hits=24, stratum="low"
    ) + make_rows(exposed_n=80, exposed_hits=24, control_n=80, control_hits=64, stratum="high")
    dataset = Dataset(template_key=template.key, rows=rows)
    outcome = evaluate(dataset, template)
    assert outcome.stability["sign_reversed_across_strata"] is True
    assert outcome.outcome == str(ResultOutcome.REJECTED)
    assert "sign" in outcome.summary


def test_a_real_but_insignificant_difference_is_inconclusive() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    # 8 points apart, but on 40 rows a side: over the effect threshold, under
    # the noise floor.
    dataset = make_dataset(exposed_n=40, exposed_hits=22, control_n=40, control_hits=19)
    outcome = evaluate(dataset, template)
    assert outcome.outcome == str(ResultOutcome.INCONCLUSIVE)
    assert outcome.p_value is not None and outcome.p_value > 0.05
    assert "noise" in outcome.summary


def test_metrics_record_the_thresholds_the_call_was_made_with() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=200, exposed_hits=140, control_n=200, control_hits=80)
    outcome = evaluate(dataset, template)
    for key in ("expected_direction", "signed_difference_pp", "n_exposed", "n_control"):
        assert key in outcome.metrics


# -- the critic -----------------------------------------------------------


def test_critic_runs_every_declared_check() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=200, exposed_hits=140, control_n=200, control_hits=80)
    outcome = evaluate(dataset, template)
    result = review(dataset, outcome, template)
    assert set(result.checks) == set(CHECK_NAMES)


def test_critic_fails_a_dataset_that_reads_the_outcome_before_the_exposure() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=60, exposed_hits=40, control_n=60, control_hits=20)
    dataset.rows[0] = replace(dataset.rows[0], outcome_at=dataset.rows[0].exposure_at)
    outcome = evaluate(dataset, template)
    result = review(dataset, outcome, template)
    assert result.checks["look_ahead_bias"] == str(CriticVerdict.FAIL)
    assert result.verdict == str(CriticVerdict.FAIL)


def test_critic_asks_for_more_data_on_a_thin_sample() -> None:
    template = TEMPLATES_BY_KEY["volume-spike-survival"]
    dataset = make_dataset(exposed_n=5, exposed_hits=3, control_n=5, control_hits=1)
    outcome = evaluate(dataset, template)
    result = review(dataset, outcome, template)
    assert result.checks["sample_size"] == str(CriticVerdict.NEEDS_MORE_DATA)
    assert result.verdict != str(CriticVerdict.PASS)
    assert result.note_text != "No objection recorded."


def test_supported_requires_a_passing_critic() -> None:
    supported = str(ResultOutcome.SUPPORTED)
    assert hypothesis_status(supported, str(CriticVerdict.PASS)) == str(
        HypothesisStatus.SUPPORTED
    )
    for verdict in (CriticVerdict.FAIL, CriticVerdict.NEEDS_MORE_DATA):
        assert hypothesis_status(supported, str(verdict)) == str(HypothesisStatus.INCONCLUSIVE)


def test_a_rejection_stands_whatever_the_critic_says() -> None:
    for verdict in CriticVerdict:
        assert hypothesis_status(str(ResultOutcome.REJECTED), str(verdict)) == str(
            HypothesisStatus.REJECTED
        )


# -- the dataset ----------------------------------------------------------


def test_dataset_hash_is_stable_under_row_order() -> None:
    dataset = make_dataset(exposed_n=20, exposed_hits=10, control_n=20, control_hits=5)
    first = dataset.hash()
    dataset.rows.reverse()
    assert dataset.hash() == first


def test_dataset_hash_changes_when_an_outcome_changes() -> None:
    dataset = make_dataset(exposed_n=20, exposed_hits=10, control_n=20, control_hits=5)
    first = dataset.hash()
    dataset.rows[0] = replace(dataset.rows[0], outcome=not dataset.rows[0].outcome)
    assert dataset.hash() != first


def test_chronological_split_never_puts_a_later_row_in_the_first_half() -> None:
    dataset = make_dataset(exposed_n=30, exposed_hits=15, control_n=30, control_hits=10)
    first, second = dataset.split()
    assert first and second
    assert max(row.exposure_at for row in first) <= min(row.exposure_at for row in second)
