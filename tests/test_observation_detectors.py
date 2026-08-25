"""Detector unit tests.

Each detector is a pure function over a window, so these tests build windows
directly instead of going through the database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.providers.source import TokenRef
from app.services.observation.detectors import (
    DetectorParams,
    holder_acceleration,
    liquidity_change,
    narrative_acceleration,
    social_onchain_divergence,
    social_velocity,
    token_survival_anomaly,
    unusual_transaction_pattern,
    volume_acceleration,
    wallet_concentration_change,
)
from app.services.observation.windows import (
    build_social_window,
    build_token_window,
    strength,
)

BASE = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
PARAMS = DetectorParams()

REF = TokenRef(
    address="DEMOTESTxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    symbol="TEST",
    name="test",
    decimals=6,
    launch_time=BASE - timedelta(hours=10),
    launchpad="demo",
)


def window(**series: list[float | int | None]):
    """Build a token window from parallel series, newest last."""
    length = len(next(iter(series.values())))
    snapshots = []
    for index in range(length):
        row = {"observed_at": BASE - timedelta(hours=length - 1 - index)}
        for name, values in series.items():
            row[name] = values[index]
        snapshots.append(row)
    return build_token_window(REF, snapshots)


def social(counts: list[int], *, terms: list[str] | None = None):
    """Build a social window from per-hour mention counts, newest last."""
    posts = []
    for offset, count in enumerate(reversed(counts)):
        for index in range(count):
            posts.append(
                {
                    "external_id": f"p{offset}-{index}",
                    "account_external_id": f"a{index % 3}",
                    "posted_at": BASE - timedelta(hours=offset, minutes=index),
                    "text": "x",
                    "matched_terms": terms or ["memecoin"],
                }
            )
    return build_social_window(posts, window_end=BASE, window_hours=len(counts))


# -- helpers ---------------------------------------------------------------


def test_strength_never_returns_zero_for_a_detector_that_fired():
    """A reported anomaly with score 0.00 reads as a bug."""
    assert strength(3.0, 3.0, 12.0) == pytest.approx(0.1)
    assert strength(12.0, 3.0, 12.0) == pytest.approx(1.0)
    assert 0.1 < strength(6.0, 3.0, 12.0) < 1.0


# -- on-chain --------------------------------------------------------------


def test_volume_acceleration_fires_on_a_real_jump():
    result = volume_acceleration(window(volume_usd=[100, 105, 98, 102, 600]), PARAMS)
    assert result is not None
    assert result.anomaly_type == "VOLUME_ACCELERATION"
    assert result.measured["ratio"] == pytest.approx(6.0, abs=0.2)
    assert result.baseline["thresholds"]["volume_ratio"] == 3.0


def test_volume_acceleration_ignores_noise():
    assert volume_acceleration(window(volume_usd=[100, 105, 98, 102, 130]), PARAMS) is None


def test_detector_returns_none_when_the_field_was_never_measured():
    """No measurement means no verdict — not a verdict of zero."""
    assert volume_acceleration(window(volume_usd=[None, None, None]), PARAMS) is None
    assert liquidity_change(window(liquidity_usd=[None, None]), PARAMS) is None


def test_liquidity_change_reports_direction():
    withdrawn = liquidity_change(window(liquidity_usd=[100_000, 38_000]), PARAMS)
    assert withdrawn is not None
    assert withdrawn.measured["change_pct"] == pytest.approx(-0.62, abs=0.01)
    assert "withdrawn" in withdrawn.explanation

    added = liquidity_change(window(liquidity_usd=[100_000, 200_000]), PARAMS)
    assert added is not None
    assert "added" in added.explanation


def test_liquidity_change_ignores_a_small_move():
    assert liquidity_change(window(liquidity_usd=[100_000, 95_000]), PARAMS) is None


def test_concentration_change_fires_on_a_jump():
    result = wallet_concentration_change(
        window(holder_concentration_top10=[0.28, 0.28, 0.29, 0.28, 0.71]), PARAMS
    )
    assert result is not None
    assert result.measured["jump"] == pytest.approx(0.43, abs=0.01)


def test_holder_acceleration_compares_growth_not_level():
    result = holder_acceleration(window(holders=[100, 110, 120, 130, 200]), PARAMS)
    assert result is not None
    assert result.measured["holder_growth"] == 70

    steady = holder_acceleration(window(holders=[100, 110, 120, 130, 141]), PARAMS)
    assert steady is None


def test_buy_share_deviation():
    result = unusual_transaction_pattern(
        window(buys=[52, 52, 52, 52, 80], sells=[48, 48, 48, 48, 20]), PARAMS
    )
    assert result is not None
    assert result.measured["buy_share"] == pytest.approx(0.8, abs=0.01)


def test_survival_anomaly_needs_age_liquidity_and_quiet():
    old_quiet = window(
        age_seconds=[8 * 86_400] * 3,
        liquidity_usd=[60_000] * 3,
        volume_usd=[1_000] * 3,
    )
    assert token_survival_anomaly(old_quiet, PARAMS) is not None

    young = window(
        age_seconds=[86_400] * 3, liquidity_usd=[60_000] * 3, volume_usd=[1_000] * 3
    )
    assert token_survival_anomaly(young, PARAMS) is None

    busy = window(
        age_seconds=[8 * 86_400] * 3, liquidity_usd=[60_000] * 3, volume_usd=[40_000] * 3
    )
    assert token_survival_anomaly(busy, PARAMS) is None

    illiquid = window(
        age_seconds=[8 * 86_400] * 3, liquidity_usd=[500] * 3, volume_usd=[10] * 3
    )
    assert token_survival_anomaly(illiquid, PARAMS) is None


# -- social ----------------------------------------------------------------


def test_social_velocity_fires_on_a_mention_spike():
    result = social_velocity(social([1, 1, 2, 1, 8]), PARAMS)
    assert result is not None
    assert result.measured["mentions_last_hour"] == 8
    assert result.measured["unique_accounts"] >= 1


def test_social_velocity_ignores_steady_chatter():
    assert social_velocity(social([4, 5, 4, 5, 6]), PARAMS) is None


def test_divergence_requires_flat_participation():
    quiet_chain = window(holders=[100, 110, 120, 130, 140])
    assert social_onchain_divergence(quiet_chain, social([1, 1, 1, 1, 8]), PARAMS) is not None


def test_divergence_does_not_fire_when_participation_moved_too():
    """Attention plus participation is a rally, not a divergence."""
    busy_chain = window(holders=[100, 110, 120, 130, 300])
    assert social_onchain_divergence(busy_chain, social([1, 1, 1, 1, 8]), PARAMS) is None


def test_narrative_acceleration_names_the_term():
    results = narrative_acceleration(social([1, 1, 1, 1, 9], terms=["AI agent"]), PARAMS)
    assert results
    assert results[0].measured["term"] == "AI agent"
    assert results[0].measured["mentions_last_hour"] == 9


def test_narrative_acceleration_is_silent_on_steady_terms():
    assert narrative_acceleration(social([5, 5, 5, 5, 5]), PARAMS) == []


def test_every_candidate_records_the_thresholds_it_used():
    """An anomaly must be re-checkable without re-running the pipeline."""
    result = volume_acceleration(window(volume_usd=[100, 100, 100, 900]), PARAMS)
    assert result is not None
    assert set(result.baseline["thresholds"]) == {"volume_ratio", "volume_ratio_saturation"}
    assert result.detector.endswith("-v1")
