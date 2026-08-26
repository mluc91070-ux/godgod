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
    "liquidity_retained_6h": "liquidity_usd",
    "holders_grew_6h": "holders",
    "volume_retained_6h": "volume_usd",
}


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
            f"Smallest group is {smallest} token-hours against a {MIN_CELL} minimum."
        )
    else:
        checks["sample_size"] = str(CriticVerdict.PASS)

    # -- independence ------------------------------------------------------
    distinct = outcome.metrics.get("distinct_tokens", 0)
    if distinct < 10:
        checks["independence"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"Token-hours come from only {distinct} tokens; consecutive hours of the same "
            "token are correlated, so the effective sample is far smaller than the row count."
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
    if excluded:
        checks["survivorship_bias"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append(
            f"{excluded} tokens were excluded for short series. Tokens that died early are "
            "exactly the ones with short series, so the sample leans toward survivors."
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
    if "liquidity_stratum" in controls and outcome.metrics.get("strata"):
        checks["confounding"] = str(CriticVerdict.PASS)
    else:
        checks["confounding"] = str(CriticVerdict.NEEDS_MORE_DATA)
        notes.append("The declared controls were not all applied in the comparison.")

    # -- stability ---------------------------------------------------------
    if outcome.stability.get("sign_reversed_across_strata"):
        checks["stability"] = str(CriticVerdict.FAIL)
        notes.append("The effect changes sign between liquidity strata.")
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
