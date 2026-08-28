"""The experiment engine.

Takes a hypothesis, builds its dataset, compares exposed against control, and
records everything needed to re-run the comparison: dataset version and hash,
features, parameters, sample size, periods, and limitations.

The result is whatever the data says. `INCONCLUSIVE` is a real answer and is
returned as often as the data deserves it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import ResultOutcome
from app.services.research.dataset import Dataset, DatasetRow
from app.services.research.stats import ProportionTest, cohens_h, two_proportion_test
from app.services.research.templates import HypothesisTemplate

MIN_CELL = 30
"""Below this per group, the comparison is reported but not believed."""


@dataclass
class StratumResult:
    stratum: str
    test: ProportionTest


@dataclass
class ExperimentOutcome:
    outcome: str
    summary: str
    metrics: dict[str, Any]
    effect_size: float | None
    p_value: float | None
    confidence: float
    limitations: list[str] = field(default_factory=list)
    strata: list[StratumResult] = field(default_factory=list)
    pooled: ProportionTest | None = None
    stability: dict[str, Any] = field(default_factory=dict)


def _rates(rows: list[DatasetRow]) -> tuple[int, int, int, int]:
    exposed = [row for row in rows if row.exposed]
    controls = [row for row in rows if not row.exposed]
    return (
        sum(1 for row in exposed if row.outcome),
        len(exposed),
        sum(1 for row in controls if row.outcome),
        len(controls),
    )


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def evaluate(dataset: Dataset, template: HypothesisTemplate) -> ExperimentOutcome:
    """Compare exposed against control, pooled and per stratum."""
    successes_a, n_a, successes_b, n_b = _rates(dataset.rows)
    pooled = two_proportion_test(successes_a, n_a, successes_b, n_b)

    limitations: list[str] = []
    if not dataset.rows:
        return ExperimentOutcome(
            outcome=str(ResultOutcome.INCONCLUSIVE),
            summary="No measurement met the sample definition. Nothing was tested.",
            metrics={"n_exposed": 0, "n_control": 0},
            effect_size=None,
            p_value=None,
            confidence=0.0,
            limitations=["empty dataset"],
        )

    if n_a == 0 or n_b == 0:
        return ExperimentOutcome(
            outcome=str(ResultOutcome.INCONCLUSIVE),
            summary=(
                f"One side of the comparison is empty ({n_a} exposed, {n_b} control), "
                "so there is nothing to compare."
            ),
            metrics={"n_exposed": n_a, "n_control": n_b},
            effect_size=None,
            p_value=None,
            confidence=0.0,
            limitations=["one empty group"],
            pooled=pooled,
        )

    strata: list[StratumResult] = []
    for name in sorted({row.stratum for row in dataset.rows}):
        subset = [row for row in dataset.rows if row.stratum == name]
        s_a, sn_a, s_b, sn_b = _rates(subset)
        if sn_a and sn_b:
            strata.append(StratumResult(name, two_proportion_test(s_a, sn_a, s_b, sn_b)))

    signs = {_sign(item.test.difference) for item in strata if item.test.difference != 0}
    sign_reversed = len(signs) > 1

    first_half, second_half = dataset.split()
    halves = {}
    for label, subset in (("first_half", first_half), ("second_half", second_half)):
        h_a, hn_a, h_b, hn_b = _rates(subset)
        halves[label] = (
            two_proportion_test(h_a, hn_a, h_b, hn_b).difference if hn_a and hn_b else None
        )
    stable_over_time = (
        None
        if halves["first_half"] is None or halves["second_half"] is None
        else _sign(halves["first_half"]) == _sign(halves["second_half"])
    )

    signed_difference_pp = pooled.difference_pp * template.expected_direction
    """Positive when the effect points the way the hypothesis predicted."""
    small_sample = min(n_a, n_b) < MIN_CELL

    if small_sample:
        limitations.append(
            f"smallest group has {min(n_a, n_b)} measurements, below the {MIN_CELL} needed "
            "to believe a difference of this size"
        )
    if len(dataset.tokens) < 10:
        limitations.append(
            f"only {len(dataset.tokens)} distinct tokens; consecutive measurements of one "
            "token are not independent observations"
        )
    if sign_reversed:
        limitations.append(f"the effect changes sign between {template.stratum_label}s")
    if stable_over_time is False:
        limitations.append("the effect changes sign between the first and second half")

    # The falsification rule was written before the data was seen. It is applied
    # as written — including its direction, so an effect pointing the opposite
    # way to the prediction falsifies rather than confirms.
    wrong_direction = signed_difference_pp <= -template.min_effect_pp
    too_small_effect = abs(signed_difference_pp) < template.min_effect_pp
    falsified = wrong_direction or too_small_effect or sign_reversed

    if small_sample:
        # A sample this size cannot settle the question either way. Saying
        # "rejected" here would dress up noise as a verdict.
        outcome = str(ResultOutcome.INCONCLUSIVE)
        seen = (
            "in the predicted direction"
            if signed_difference_pp > 0
            else "against the predicted direction"
        )
        summary = (
            f"Difference of {pooled.difference_pp:+.1f} points {seen} "
            f"(exposed {pooled.rate_a:.0%} vs control {pooled.rate_b:.0%}, "
            f"{n_a} vs {n_b} measurements). The smallest group holds {min(n_a, n_b)} rows, "
            f"below the {MIN_CELL} needed to judge a difference of this size, so the "
            "falsification rule is not applied to a sample that cannot support it."
        )
        confidence = 0.15
    elif falsified:
        outcome = str(ResultOutcome.REJECTED)
        if sign_reversed:
            reason = f"the sign reverses between {template.stratum_label}s"
        elif wrong_direction:
            reason = (
                f"the effect points the opposite way to the prediction "
                f"({pooled.difference_pp:+.1f} points)"
            )
        else:
            reason = (
                f"the difference is {abs(pooled.difference_pp):.1f} points, below the "
                f"{template.min_effect_pp:.0f}-point threshold"
            )
        summary = (
            f"Rejected by its own falsification rule: {reason}. "
            f"Exposed {pooled.rate_a:.0%} vs control {pooled.rate_b:.0%} "
            f"({n_a} vs {n_b} measurements)."
        )
        confidence = 0.35
    elif pooled.p_value is not None and pooled.p_value > 0.05:
        outcome = str(ResultOutcome.INCONCLUSIVE)
        summary = (
            f"Difference of {pooled.difference_pp:+.1f} points "
            f"(exposed {pooled.rate_a:.0%} vs control {pooled.rate_b:.0%}), "
            f"p={pooled.p_value:.3f}. Not distinguishable from noise."
        )
        confidence = 0.2
    else:
        outcome = str(ResultOutcome.SUPPORTED)
        summary = (
            f"Difference of {pooled.difference_pp:+.1f} points "
            f"(exposed {pooled.rate_a:.0%} vs control {pooled.rate_b:.0%}), "
            f"p={pooled.p_value:.3f}, holding its sign across {template.stratum_label}s."
        )
        confidence = 0.5

    return ExperimentOutcome(
        outcome=outcome,
        summary=summary,
        metrics={
            "rate_exposed": pooled.rate_a,
            "rate_control": pooled.rate_b,
            "difference_pp": pooled.difference_pp,
            "z": pooled.z,
            "n_exposed": n_a,
            "n_control": n_b,
            "distinct_tokens": len(dataset.tokens),
            "strata": {
                item.stratum: {
                    "difference_pp": item.test.difference_pp,
                    "n_exposed": item.test.n_a,
                    "n_control": item.test.n_b,
                }
                for item in strata
            },
            "first_half_difference": halves["first_half"],
            "second_half_difference": halves["second_half"],
            "expected_direction": template.expected_direction,
            "signed_difference_pp": round(signed_difference_pp, 2),
            "falsification_condition_met": falsified,
            "sample_too_small_to_judge": small_sample,
            "excluded_rows": dataset.excluded,
        },
        effect_size=cohens_h(pooled.rate_a, pooled.rate_b),
        p_value=pooled.p_value,
        confidence=confidence,
        limitations=limitations,
        strata=strata,
        pooled=pooled,
        stability={
            "sign_reversed_across_strata": sign_reversed,
            "stratified_by": template.stratify_by,
            "stable_across_time": stable_over_time,
        },
    )
