"""Hypothesis templates.

A template turns an anomaly into a *complete* hypothesis: population, sample,
timeframe, baseline, expected result and — the part that makes it a hypothesis
at all — the condition that would falsify it.

Templates are deterministic and parameterised. Model-written hypotheses come
with the external integrations; until then the wording is fixed and the
thinking lives in the trigger, the outcome and the falsification rule.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import AnomalyType
from app.services.observation.detectors import DetectorParams
from app.services.observation.windows import TokenWindow, median, ratio


@dataclass(frozen=True)
class HypothesisTemplate:
    """One testable question, and everything needed to test it."""

    key: str
    anomaly_type: str
    question: str
    statement: str
    population: str
    sample_definition: str
    timeframe: str
    baseline: str
    expected_result: str
    falsification_condition: str
    variables: dict[str, Any]

    trigger: Callable[[TokenWindow, DetectorParams], bool]
    """Exposure: did the condition hold at this point in the series?"""

    outcome: Callable[[dict[str, Any], dict[str, Any]], bool | None]
    """Outcome, measured strictly later. None when it cannot be measured."""

    outcome_label: str
    horizon_hours: int
    expected_direction: int
    """+1 if exposure should raise the outcome rate, -1 if it should lower it.

    Without this a hypothesis is unfalsifiable in practice: an effect in the
    opposite direction to the prediction would otherwise count as confirmation
    as long as it was large enough.
    """
    min_effect_pp: float = 5.0
    """Below this difference in percentage points the hypothesis is falsified."""

    features: list[str] = field(default_factory=list)


def _volume_spike(window: TokenWindow, params: DetectorParams) -> bool:
    observed = ratio(window.value("volume_usd"), median(window.series("volume_usd")))
    return observed is not None and observed >= params.volume_ratio


def _liquidity_withdrawn(window: TokenWindow, params: DetectorParams) -> bool:
    latest = window.value("liquidity_usd")
    previous = window.previous("liquidity_usd")
    if latest is None or not previous:
        return False
    return (latest - previous) / previous <= -params.liquidity_change_pct


def _concentration_high(window: TokenWindow, params: DetectorParams) -> bool:
    measured = window.value("holder_concentration_top10")
    base = median(window.series("holder_concentration_top10"))
    if measured is None or base is None:
        return False
    return (measured - base) >= params.concentration_jump


def _buy_share_spike(window: TokenWindow, params: DetectorParams) -> bool:
    buys, sells = window.value("buys"), window.value("sells")
    if buys is None or sells is None or (buys + sells) <= 0:
        return False
    share = buys / (buys + sells)
    historical = [
        row["buys"] / (row["buys"] + row["sells"])
        for row in window.history
        if row.get("buys") is not None
        and row.get("sells") is not None
        and (row["buys"] + row["sells"]) > 0
    ]
    base = median(historical)
    return base is not None and (share - base) >= params.buy_share_deviation


def _holder_spike(window: TokenWindow, params: DetectorParams) -> bool:
    deltas = [delta for delta in window.deltas("holders") if delta > 0]
    latest = window.value("holders")
    previous = window.previous("holders")
    if latest is None or previous is None:
        return False
    observed = ratio(latest - previous, median(deltas))
    return observed is not None and observed >= params.holder_growth_ratio


def _quiet_survivor(window: TokenWindow, params: DetectorParams) -> bool:
    age = window.value("age_seconds")
    liquidity = window.value("liquidity_usd")
    volume = window.value("volume_usd")
    if age is None or liquidity is None or volume is None or liquidity <= 0:
        return False
    return (
        age / 86_400 >= params.survival_age_days
        and liquidity >= params.survival_liquidity_usd
        and volume / liquidity < params.survival_quiet_volume_ratio
    )


# -- outcomes ---------------------------------------------------------------


def _liquidity_held(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    """Did liquidity keep at least 80% of its starting value?"""
    before, after = start.get("liquidity_usd"), later.get("liquidity_usd")
    if before is None or after is None or before <= 0:
        return None
    return after >= 0.8 * before


def _holders_grew(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    before, after = start.get("holders"), later.get("holders")
    if before is None or after is None or before <= 0:
        return None
    return after > before * 1.02


def _volume_held(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    before, after = start.get("volume_usd"), later.get("volume_usd")
    if before is None or after is None or before <= 0:
        return None
    return after >= 0.5 * before


TEMPLATES: tuple[HypothesisTemplate, ...] = (
    HypothesisTemplate(
        key="volume-spike-survival",
        anomaly_type=str(AnomalyType.VOLUME_ACCELERATION),
        question="Does a volume spike predict that liquidity holds six hours later?",
        statement=(
            "Token-hours where volume exceeds three times its six-hour median are followed "
            "by liquidity retaining at least 80% of its value six hours later more often "
            "than token-hours without such a spike."
        ),
        population="Observed Solana tokens with at least seven consecutive hourly measurements",
        sample_definition=(
            "Token-hours with a full six-hour trailing window and a measurement six hours later"
        ),
        timeframe="6h trailing window for exposure, outcome measured at +6h",
        baseline="Token-hours in the same liquidity stratum without a volume spike",
        expected_result="Higher liquidity-retention rate among spiked token-hours",
        falsification_condition=(
            "The retention rate among spiked token-hours is not at least 5 percentage points "
            "higher than the baseline, or the sign reverses between liquidity strata"
        ),
        variables={
            "independent": ["volume_over_median"],
            "dependent": ["liquidity_retained_6h"],
            "controls": ["liquidity_stratum", "token_age_hours"],
        },
        trigger=_volume_spike,
        outcome=_liquidity_held,
        outcome_label="liquidity retained >= 80% after 6h",
        horizon_hours=6,
        expected_direction=1,
        features=["volume_usd", "liquidity_usd", "holders", "age_seconds"],
    ),
    HypothesisTemplate(
        key="divergence-participation",
        anomaly_type=str(AnomalyType.SOCIAL_ONCHAIN_DIVERGENCE),
        question="Is attention without participation followed by holder growth anyway?",
        statement=(
            "Token-hours where mentions rise at least threefold while holder growth stays "
            "flat are followed by holder growth six hours later less often than token-hours "
            "without that divergence."
        ),
        population="Observed Solana tokens with social mentions and hourly measurements",
        sample_definition="Token-hours with a full trailing window and a +6h measurement",
        timeframe="6h window for exposure, outcome measured at +6h",
        baseline="Token-hours in the same liquidity stratum without divergence",
        expected_result="Lower holder-growth rate among divergent token-hours",
        falsification_condition=(
            "The holder-growth rate among divergent token-hours is not at least 5 percentage "
            "points lower than the baseline, or the sign reverses between liquidity strata"
        ),
        variables={
            "independent": ["social_velocity_ratio", "holder_growth_ratio"],
            "dependent": ["holders_grew_6h"],
            "controls": ["liquidity_stratum"],
        },
        trigger=_holder_spike,
        outcome=_holders_grew,
        outcome_label="holders grew more than 2% after 6h",
        horizon_hours=6,
        expected_direction=-1,
        features=["holders", "liquidity_usd", "volume_usd"],
    ),
    HypothesisTemplate(
        key="withdrawal-death",
        anomaly_type=str(AnomalyType.LIQUIDITY_CHANGE),
        question="Does a large liquidity withdrawal predict further collapse?",
        statement=(
            "Token-hours with a liquidity withdrawal of at least 35% are followed by further "
            "liquidity loss six hours later more often than token-hours without one."
        ),
        population="Observed Solana tokens with hourly liquidity measurements",
        sample_definition="Token-hours with a full trailing window and a +6h measurement",
        timeframe="one step for exposure, outcome measured at +6h",
        baseline="Token-hours in the same liquidity stratum with no withdrawal",
        expected_result="Lower liquidity-retention rate after a withdrawal",
        falsification_condition=(
            "The retention rate after a withdrawal is not at least 5 percentage points lower than "
            "the baseline, or the sign reverses between liquidity strata"
        ),
        variables={
            "independent": ["liquidity_change_pct"],
            "dependent": ["liquidity_retained_6h"],
            "controls": ["liquidity_stratum"],
        },
        trigger=_liquidity_withdrawn,
        outcome=_liquidity_held,
        outcome_label="liquidity retained >= 80% after 6h",
        horizon_hours=6,
        expected_direction=-1,
        features=["liquidity_usd", "volume_usd"],
    ),
    HypothesisTemplate(
        key="concentration-withdrawal",
        anomaly_type=str(AnomalyType.WALLET_CONCENTRATION_CHANGE),
        question="Does a concentration jump precede liquidity leaving?",
        statement=(
            "Token-hours where top-10 concentration jumps at least 0.15 above its window "
            "median are followed by liquidity retention six hours later less often than "
            "token-hours without such a jump."
        ),
        population="Observed Solana tokens with concentration measurements",
        sample_definition="Token-hours with a full trailing window and a +6h measurement",
        timeframe="6h window for exposure, outcome measured at +6h",
        baseline="Token-hours in the same liquidity stratum without a concentration jump",
        expected_result="Lower liquidity-retention rate after a concentration jump",
        falsification_condition=(
            "The retention rate after a concentration jump is not at least 5 percentage points "
            "lower than the baseline, or the sign reverses between liquidity strata"
        ),
        variables={
            "independent": ["concentration_jump"],
            "dependent": ["liquidity_retained_6h"],
            "controls": ["liquidity_stratum"],
        },
        trigger=_concentration_high,
        outcome=_liquidity_held,
        outcome_label="liquidity retained >= 80% after 6h",
        horizon_hours=6,
        expected_direction=-1,
        features=["holder_concentration_top10", "liquidity_usd"],
    ),
    HypothesisTemplate(
        key="buy-pressure-reversal",
        anomaly_type=str(AnomalyType.UNUSUAL_TRANSACTION_PATTERN),
        question="Does a buy-share spike hold up, or reverse?",
        statement=(
            "Token-hours where buy share rises at least 10 points above its window median "
            "are followed by volume retention six hours later more often than token-hours "
            "without such a rise."
        ),
        population="Observed Solana tokens with buy/sell counts",
        sample_definition="Token-hours with a full trailing window and a +6h measurement",
        timeframe="6h window for exposure, outcome measured at +6h",
        baseline="Token-hours in the same liquidity stratum without a buy-share spike",
        expected_result="Higher volume-retention rate after a buy-share spike",
        falsification_condition=(
            "The volume-retention rate after a buy-share spike is not at least 5 percentage points "
            "higher than the baseline, or the sign reverses between liquidity strata"
        ),
        variables={
            "independent": ["buy_share_deviation"],
            "dependent": ["volume_retained_6h"],
            "controls": ["liquidity_stratum"],
        },
        trigger=_buy_share_spike,
        outcome=_volume_held,
        outcome_label="volume retained >= 50% after 6h",
        horizon_hours=6,
        expected_direction=1,
        features=["buys", "sells", "volume_usd"],
    ),
    HypothesisTemplate(
        key="quiet-survivor",
        anomaly_type=str(AnomalyType.TOKEN_SURVIVAL_ANOMALY),
        question="Do quiet survivors keep their liquidity better than active tokens?",
        statement=(
            "Token-hours belonging to tokens older than seven days that are liquid but "
            "trading below a quarter of their liquidity are followed by liquidity retention "
            "six hours later more often than other token-hours."
        ),
        population="Observed Solana tokens with age and liquidity measurements",
        sample_definition="Token-hours with a full trailing window and a +6h measurement",
        timeframe="6h window for exposure, outcome measured at +6h",
        baseline="Token-hours in the same liquidity stratum that are not quiet survivors",
        expected_result="Higher liquidity-retention rate among quiet survivors",
        falsification_condition=(
            "The retention rate among quiet survivors is not at least 5 percentage points higher "
            "than the baseline, or the sign reverses between liquidity strata"
        ),
        variables={
            "independent": ["age_days", "volume_over_liquidity"],
            "dependent": ["liquidity_retained_6h"],
            "controls": ["liquidity_stratum"],
        },
        trigger=_quiet_survivor,
        outcome=_liquidity_held,
        outcome_label="liquidity retained >= 80% after 6h",
        horizon_hours=6,
        expected_direction=1,
        features=["age_seconds", "liquidity_usd", "volume_usd"],
    ),
)

TEMPLATES_BY_ANOMALY: dict[str, HypothesisTemplate] = {
    template.anomaly_type: template for template in TEMPLATES
}
TEMPLATES_BY_KEY: dict[str, HypothesisTemplate] = {
    template.key: template for template in TEMPLATES
}
