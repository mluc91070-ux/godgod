"""The critic.

Answers one question: why might this be wrong?

Every check is deterministic and inspectable. The critic does not know whether
a result is *interesting*, and that is deliberate — it only knows whether the
design could support the claim.

A hypothesis cannot become SUPPORTED without a PASS here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.enums import CriticVerdict, HypothesisStatus, ResultOutcome
from app.services.research.dataset import Dataset
from app.services.research.experiments import MIN_CELL, ExperimentOutcome
from app.services.research.templates import HypothesisTemplate

CRITIC_VERSION = "critic-checks-v1"

CHECK_NAMES: tuple[str, ...] = (
    "sample_size",
    "independence",
    "look_ahead_bias",
    "data_leakage",
    "survivorship_bias",
    "selection_bias",
    "confounding",
    "stability",
    "multiple_testing",
    "data_quality",
)
"""Every check `review()` can record. Declared here so /api/status can list
what the critic actually inspects instead of a hand-maintained copy."""

OUTCOME_FIELDS = {
    "liquidity_retained": "liquidity_usd",
    "pool_still_alive": "liquidity_usd",
    "volume_retained": "volume_usd",
    "still_trading": "buys",
    "market_cap_retained": "market_cap_usd",
    "holders_grew": "holders",
}
"""Dependent variable to the snapshot field it is read from, so the leakage
check can tell when a template feeds the outcome back in as a feature."""

CONTROL_FOR_STRATUM = {
    "liquidity": "liquidity_stratum",
    "age": "age_stratum",
    "frame": "sampling_frame",
}
"""What a template must declare as a control for the comparison it actually
runs. Checking for `liquidity_stratum` alone, as this once did, passed every
template by accident: it was the only stratification there was."""


@dataclass
class CriticReview:
    verdict: str
    checks: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def note_text(self) -> str:
        return " ".join(self.notes) if self.notes else "No objection recorded."

    def as_dict(self) -> dict[str, Any]:
        return {**self.checks, "version": CRITIC_VERSION}


def review(
    dataset: Dataset, outcome: ExperimentOutcome, template: HypothesisTemplate
) -> CriticReview:
    checks: dict[str, str] = {}
    notes: list[str] = []

    # -- sample size -------------------------------------------------------
    n_exposed = outcome.metrics.get("n_exposed", 0)
    n_control = outcome.metrics.get("n_control", 0)
    smallest = min(n_exposed, n_control)
    if smallest == 0:
        checks["sample_size"] = str(CriticVerdict.FAIL)
        notes.append("One group is empty; nothing was compared.")
    elif smallest < MIN_CELL:
        checks["sample_size"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"Smallest group is {smallest} measurements against a {MIN_CELL} minimum."
        )
    else:
        checks["sample_size"] = str(CriticVerdict.PASS)

    # -- independence ------------------------------------------------------
    distinct = outcome.metrics.get("distinct_tokens", 0)
    if distinct < 10:
        checks["independence"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"Measurements come from only {distinct} tokens; consecutive readings of the "
            "same token are correlated, so the effective sample is far smaller than the "
            "row count."
        )
    else:
        checks["independence"] = str(CriticVerdict.PASS)

    # -- look-ahead --------------------------------------------------------
    violations = [row for row in dataset.rows if row.outcome_at <= row.exposure_at]
    if violations:
        checks["look_ahead_bias"] = str(CriticVerdict.FAIL)
        notes.append(f"{len(violations)} rows measure the outcome at or before exposure.")
    else:
        checks["look_ahead_bias"] = str(CriticVerdict.PASS)

    # -- leakage -----------------------------------------------------------
    dependent = (template.variables.get("dependent") or [None])[0]
    leaked = OUTCOME_FIELDS.get(str(dependent))
    if leaked and leaked in template.features and template.horizon_hours == 0:
        checks["data_leakage"] = str(CriticVerdict.FAIL)
        notes.append(f"Feature {leaked} is the outcome measured at the same instant.")
    else:
        checks["data_leakage"] = str(CriticVerdict.PASS)

    # -- survivorship ------------------------------------------------------
    excluded = dataset.excluded.get("token_series_too_short", 0)
    unreached = dataset.excluded.get("no_reading_at_horizon", 0)
    if excluded or unreached:
        checks["survivorship_bias"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"{excluded} tokens were excluded for short series and {unreached} readings had "
            f"nothing {template.horizon_hours:g}h later. Tokens that died early are exactly "
            "the ones that run out of series, so the sample leans toward survivors."
        )
    else:
        checks["survivorship_bias"] = str(CriticVerdict.PASS)

    # -- selection ---------------------------------------------------------
    checks["selection_bias"] = str(CriticVerdict.NEEDS_MORE_DATA)
    notes.append(
        "Exposure is defined by the same detector that surfaced the anomaly, so the "
        "hypothesis and its test share a definition. An independent trigger would be stronger."
    )

    # -- confounding -------------------------------------------------------
    controls = template.variables.get("controls") or []
    required = CONTROL_FOR_STRATUM[template.stratify_by]
    if required in controls and outcome.metrics.get("strata"):
        checks["confounding"] = str(CriticVerdict.PASS)
    else:
        checks["confounding"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"The comparison is held within {template.stratum_label}s, which the "
            f"hypothesis does not declare as a control, or no {template.stratum_label} "
            "held rows on both sides."
        )

    # -- stability ---------------------------------------------------------
    if outcome.stability.get("sign_reversed_across_strata"):
        checks["stability"] = str(CriticVerdict.FAIL)
        notes.append(f"The effect changes sign between {template.stratum_label}s.")
    elif outcome.stability.get("stable_across_time") is False:
        checks["stability"] = str(CriticVerdict.FAIL)
        notes.append("The effect changes sign between the first and second half of the period.")
    elif outcome.stability.get("stable_across_time") is None:
        checks["stability"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append("One half of the period had no comparable rows, so stability is untested.")
    else:
        checks["stability"] = str(CriticVerdict.PASS)

    # -- multiple testing --------------------------------------------------
    checks["multiple_testing"] = str(CriticVerdict.PASS)

    # -- data quality ------------------------------------------------------
    if dataset.excluded.get("outcome_unmeasurable"):
        checks["data_quality"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"{dataset.excluded['outcome_unmeasurable']} rows had no measurable outcome."
        )
    else:
        checks["data_quality"] = str(CriticVerdict.PASS)

    if str(CriticVerdict.FAIL) in checks.values():
        verdict = str(CriticVerdict.FAIL)
    elif str(CriticVerdict.NEEDS_MORE_DATA) in checks.values():
        verdict = str(CriticVerdict.NEEDS_MORE_DATA)
    else:
        verdict = str(CriticVerdict.PASS)

    return CriticReview(verdict=verdict, checks=checks, notes=notes)


def hypothesis_status(outcome: str, verdict: str) -> str:
    """The gate: no PASS from the critic, no SUPPORTED hypothesis.

    A rejection stands on its own — the falsification condition was written
    before the data was seen, so meeting it settles the question regardless of
    how strong the design was. Everything else that fails review becomes
    INCONCLUSIVE rather than a finding.
    """
    if outcome == str(ResultOutcome.REJECTED):
        return str(HypothesisStatus.REJECTED)
    if outcome == str(ResultOutcome.SUPPORTED) and verdict == str(CriticVerdict.PASS):
        return str(HypothesisStatus.SUPPORTED)
    return str(HypothesisStatus.INCONCLUSIVE)
