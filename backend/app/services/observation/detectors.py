"""Anomaly detectors.

Every detector here is deterministic: same window in, same verdict out, no
model involved. That is the point — the expensive reasoning layer only ever
sees what these cheap functions decided was worth looking at.

Each detector records the baseline it compared against, the measurement that
fired it, and the thresholds it used, so an anomaly can be re-checked later
without re-running the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from app.core.enums import AnomalyType
from app.services.observation.windows import (
    SocialWindow,
    TokenWindow,
    median,
    ratio,
    strength,
)


@dataclass(frozen=True)
class DetectorParams:
    """Thresholds. Recorded on every anomaly so a result stays reproducible."""

    volume_ratio: float = 3.0
    volume_ratio_saturation: float = 12.0

    holder_growth_ratio: float = 3.0
    holder_growth_saturation: float = 10.0

    liquidity_change_pct: float = 0.35
    liquidity_change_saturation: float = 0.9

    concentration_jump: float = 0.15
    concentration_saturation: float = 0.5

    buy_share_deviation: float = 0.10
    buy_share_saturation: float = 0.35

    social_ratio: float = 3.0
    social_ratio_saturation: float = 12.0

    divergence_participation_ceiling: float = 1.2
    """Above this, on-chain participation moved too, so it is not divergence."""

    narrative_ratio: float = 3.0
    narrative_ratio_saturation: float = 10.0

    standing_cooldown_hours: float = 24.0
    """Cooldown for anomalies that describe a lasting state, not an event."""

    survival_age_days: float = 7.0
    survival_liquidity_usd: float = 10_000.0
    survival_quiet_volume_ratio: float = 0.25
    """Volume below this share of its own liquidity-implied baseline is quiet."""


@dataclass(frozen=True)
class AnomalyCandidate:
    anomaly_type: str
    detector: str
    score: float
    baseline: dict[str, Any]
    measured: dict[str, Any]
    explanation: str


def _params(baseline: dict[str, Any], params: DetectorParams, keys: list[str]) -> dict[str, Any]:
    """Attach the thresholds that were actually used to the baseline record."""
    values = asdict(params)
    return {**baseline, "thresholds": {key: values[key] for key in keys}}


# --------------------------------------------------------------------------
# on-chain detectors
# --------------------------------------------------------------------------


def volume_acceleration(window: TokenWindow, params: DetectorParams) -> AnomalyCandidate | None:
    measured = window.value("volume_usd")
    base = median(window.series("volume_usd"))
    observed_ratio = ratio(measured, base)
    if observed_ratio is None or observed_ratio < params.volume_ratio:
        return None
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.VOLUME_ACCELERATION),
        detector="volume-acceleration-v1",
        score=strength(observed_ratio, params.volume_ratio, params.volume_ratio_saturation),
        baseline=_params(
            {"median_volume_usd": base, "window_points": len(window.history)},
            params,
            ["volume_ratio", "volume_ratio_saturation"],
        ),
        measured={"volume_usd": measured, "ratio": round(observed_ratio, 3)},
        explanation=f"volume is {observed_ratio:.1f}x its window median",
    )


def holder_acceleration(window: TokenWindow, params: DetectorParams) -> AnomalyCandidate | None:
    deltas = window.deltas("holders")
    if len(deltas) < 2:
        return None
    latest_delta = None
    if window.value("holders") is not None and window.previous("holders") is not None:
        latest_delta = window.value("holders") - window.previous("holders")
    base = median([delta for delta in deltas if delta > 0])
    observed_ratio = ratio(latest_delta, base)
    if observed_ratio is None or observed_ratio < params.holder_growth_ratio:
        return None
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.HOLDER_ACCELERATION),
        detector="holder-acceleration-v1",
        score=strength(
            observed_ratio, params.holder_growth_ratio, params.holder_growth_saturation
        ),
        baseline=_params(
            {"median_holder_growth": base},
            params,
            ["holder_growth_ratio", "holder_growth_saturation"],
        ),
        measured={"holder_growth": latest_delta, "ratio": round(observed_ratio, 3)},
        explanation=f"holder growth is {observed_ratio:.1f}x its usual step",
    )


def liquidity_change(window: TokenWindow, params: DetectorParams) -> AnomalyCandidate | None:
    measured = window.value("liquidity_usd")
    previous = window.previous("liquidity_usd")
    if measured is None or previous in (None, 0):
        return None
    change = (measured - previous) / previous
    if abs(change) < params.liquidity_change_pct:
        return None
    direction = "withdrawn" if change < 0 else "added"
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.LIQUIDITY_CHANGE),
        detector="liquidity-change-v1",
        score=strength(
            abs(change), params.liquidity_change_pct, params.liquidity_change_saturation
        ),
        baseline=_params(
            {"previous_liquidity_usd": previous},
            params,
            ["liquidity_change_pct", "liquidity_change_saturation"],
        ),
        measured={"liquidity_usd": measured, "change_pct": round(change, 4)},
        explanation=f"liquidity {direction}: {change:+.0%} in one step",
    )


def wallet_concentration_change(
    window: TokenWindow, params: DetectorParams
) -> AnomalyCandidate | None:
    measured = window.value("holder_concentration_top10")
    base = median(window.series("holder_concentration_top10"))
    if measured is None or base is None:
        return None
    jump = measured - base
    if abs(jump) < params.concentration_jump:
        return None
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.WALLET_CONCENTRATION_CHANGE),
        detector="concentration-change-v1",
        score=strength(abs(jump), params.concentration_jump, params.concentration_saturation),
        baseline=_params(
            {"median_concentration": base},
            params,
            ["concentration_jump", "concentration_saturation"],
        ),
        measured={"concentration_top10": measured, "jump": round(jump, 4)},
        explanation=f"top-10 concentration moved {jump:+.2f} against its window median",
    )


def unusual_transaction_pattern(
    window: TokenWindow, params: DetectorParams
) -> AnomalyCandidate | None:
    buys = window.value("buys")
    sells = window.value("sells")
    if buys is None or sells is None or (buys + sells) <= 0:
        return None
    share = buys / (buys + sells)

    historical = [
        row["buys"] / (row["buys"] + row["sells"])
        for row in window.history
        if row.get("buys") is not None
        and row.get("sells") is not None
        and (row["buys"] + row["sells"]) > 0
    ]
    base = median(historical)
    if base is None:
        return None

    deviation = share - base
    if abs(deviation) < params.buy_share_deviation:
        return None
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.UNUSUAL_TRANSACTION_PATTERN),
        detector="buy-share-deviation-v1",
        score=strength(abs(deviation), params.buy_share_deviation, params.buy_share_saturation),
        baseline=_params(
            {"median_buy_share": round(base, 4)},
            params,
            ["buy_share_deviation", "buy_share_saturation"],
        ),
        measured={"buy_share": round(share, 4), "deviation": round(deviation, 4)},
        explanation=f"buy share {share:.0%} against a {base:.0%} baseline",
    )


def token_survival_anomaly(
    window: TokenWindow, params: DetectorParams
) -> AnomalyCandidate | None:
    """Alive but quiet: still liquid a week in, with almost no trading.

    Unusual for a meme token, and the kind of thing worth a hypothesis rather
    than a trade.
    """
    age_seconds = window.value("age_seconds")
    liquidity = window.value("liquidity_usd")
    volume = window.value("volume_usd")
    if age_seconds is None or liquidity is None or volume is None:
        return None

    age_days = age_seconds / 86_400
    if age_days < params.survival_age_days or liquidity < params.survival_liquidity_usd:
        return None

    quiet_ratio = volume / liquidity
    if quiet_ratio >= params.survival_quiet_volume_ratio:
        return None

    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.TOKEN_SURVIVAL_ANOMALY),
        detector="survival-quiet-v1",
        score=strength(
            params.survival_quiet_volume_ratio - quiet_ratio,
            0.0,
            params.survival_quiet_volume_ratio,
        ),
        baseline=_params(
            {"age_days": round(age_days, 2), "liquidity_usd": liquidity},
            params,
            ["survival_age_days", "survival_liquidity_usd", "survival_quiet_volume_ratio"],
        ),
        measured={"volume_usd": volume, "volume_over_liquidity": round(quiet_ratio, 4)},
        explanation=(
            f"{age_days:.1f} days old, ${liquidity:,.0f} liquidity, "
            f"volume only {quiet_ratio:.1%} of it"
        ),
    )


ONCHAIN_DETECTORS: tuple[Callable[[TokenWindow, DetectorParams], AnomalyCandidate | None], ...] = (
    volume_acceleration,
    holder_acceleration,
    liquidity_change,
    wallet_concentration_change,
    unusual_transaction_pattern,
    token_survival_anomaly,
)


# --------------------------------------------------------------------------
# social detectors
# --------------------------------------------------------------------------


def social_velocity(social: SocialWindow, params: DetectorParams) -> AnomalyCandidate | None:
    base = median([float(count) for count in social.baseline_hours])
    observed_ratio = ratio(float(social.latest_hour), base)
    if observed_ratio is None or observed_ratio < params.social_ratio:
        return None
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.SOCIAL_VELOCITY),
        detector="social-velocity-v1",
        score=strength(observed_ratio, params.social_ratio, params.social_ratio_saturation),
        baseline=_params(
            {"median_hourly_mentions": base, "window_hours": social.window_hours},
            params,
            ["social_ratio", "social_ratio_saturation"],
        ),
        measured={
            "mentions_last_hour": social.latest_hour,
            "unique_accounts": social.unique_accounts_latest_hour,
            "ratio": round(observed_ratio, 3),
        },
        explanation=f"mentions are {observed_ratio:.1f}x the hourly median",
    )


def social_onchain_divergence(
    window: TokenWindow, social: SocialWindow, params: DetectorParams
) -> AnomalyCandidate | None:
    """Attention moved, participation did not."""
    social_base = median([float(count) for count in social.baseline_hours])
    social_ratio_value = ratio(float(social.latest_hour), social_base)
    if social_ratio_value is None or social_ratio_value < params.social_ratio:
        return None

    deltas = window.deltas("holders")
    holder_base = median([delta for delta in deltas if delta > 0])
    latest_delta = None
    if window.value("holders") is not None and window.previous("holders") is not None:
        latest_delta = window.value("holders") - window.previous("holders")
    participation_ratio = ratio(latest_delta, holder_base)

    if participation_ratio is None:
        return None
    if participation_ratio > params.divergence_participation_ceiling:
        return None

    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.SOCIAL_ONCHAIN_DIVERGENCE),
        detector="social-onchain-divergence-v1",
        score=strength(social_ratio_value, params.social_ratio, params.social_ratio_saturation),
        baseline=_params(
            {
                "median_hourly_mentions": social_base,
                "median_holder_growth": holder_base,
            },
            params,
            ["social_ratio", "divergence_participation_ceiling"],
        ),
        measured={
            "mentions_last_hour": social.latest_hour,
            "social_ratio": round(social_ratio_value, 3),
            "holder_growth": latest_delta,
            "participation_ratio": round(participation_ratio, 3),
        },
        explanation=(
            f"mentions {social_ratio_value:.1f}x while holder growth stayed at "
            f"{participation_ratio:.1f}x"
        ),
    )


def narrative_acceleration(
    social: SocialWindow, params: DetectorParams
) -> list[AnomalyCandidate]:
    """Per-term, across every token: which words are accelerating."""
    latest = social.term_counts(latest_hour_only=True)
    overall = social.term_counts()
    hours = max(1, social.window_hours)

    found: list[AnomalyCandidate] = []
    for term, count in latest.items():
        hourly_baseline = (overall[term] - count) / max(1, hours - 1)
        observed_ratio = ratio(float(count), hourly_baseline)
        if observed_ratio is None or observed_ratio < params.narrative_ratio:
            continue
        found.append(
            AnomalyCandidate(
                anomaly_type=str(AnomalyType.NARRATIVE_ACCELERATION),
                detector="narrative-acceleration-v1",
                score=strength(
                    observed_ratio, params.narrative_ratio, params.narrative_ratio_saturation
                ),
                baseline=_params(
                    {"term": term, "hourly_baseline": round(hourly_baseline, 3)},
                    params,
                    ["narrative_ratio", "narrative_ratio_saturation"],
                ),
                measured={"term": term, "mentions_last_hour": count},
                explanation=f'"{term}" is {observed_ratio:.1f}x its hourly baseline',
            )
        )
    return sorted(found, key=lambda candidate: candidate.score, reverse=True)


DETECTOR_NAMES: tuple[str, ...] = (
    "volume-acceleration-v1",
    "holder-acceleration-v1",
    "liquidity-change-v1",
    "concentration-change-v1",
    "buy-share-deviation-v1",
    "survival-quiet-v1",
    "social-velocity-v1",
    "social-onchain-divergence-v1",
    "narrative-acceleration-v1",
    "cluster-appearance-v1",
)
"""Every detector that can fire. Reported by /api/status."""


def new_wallet_cluster(cluster: dict[str, Any]) -> AnomalyCandidate:
    """A cluster that appeared inside the window.

    Clustering itself is not implemented — the pipeline reports clusters that
    already exist in the database, and records the method that produced them.
    """
    return AnomalyCandidate(
        anomaly_type=str(AnomalyType.NEW_WALLET_CLUSTER),
        detector="cluster-appearance-v1",
        score=float(cluster.get("confidence") or 0.5),
        baseline={"method": cluster.get("method"), "detected_by": "stored clustering"},
        measured={"size": cluster.get("size"), "label": cluster.get("label")},
        explanation=f"wallet cluster of {cluster.get('size')} appeared in the window",
    )
