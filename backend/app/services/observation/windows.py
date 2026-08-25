"""Measurement windows.

A window is what a detector compares against: a trailing series of
measurements plus the newest one. Nothing is interpolated — if a field is
missing from a snapshot it is missing from the series, and a detector that
needs it says so instead of guessing.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

from app.providers.source import TokenRef

SNAPSHOT_FIELDS = (
    "market_cap_usd",
    "liquidity_usd",
    "volume_usd",
    "holders",
    "holder_concentration_top10",
    "transactions",
    "buys",
    "sells",
    "age_seconds",
)


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def ratio(measured: float | None, baseline: float | None) -> float | None:
    """Measured over baseline, or None when the comparison is meaningless."""
    if measured is None or baseline is None or baseline <= 0:
        return None
    return measured / baseline


def bounded(value: float, low: float, high: float) -> float:
    """Map [low, high] onto [0, 1]."""
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


MIN_STRENGTH = 0.1


def strength(value: float, low: float, high: float) -> float:
    """Turn a threshold crossing into a score in [0.1, 1.0].

    A detector that fired exactly at its threshold still scored something: a
    reported anomaly with score 0.00 reads as a bug, and hides the fact that
    the detector made a real, if marginal, call.
    """
    return round(MIN_STRENGTH + (1.0 - MIN_STRENGTH) * bounded(value, low, high), 4)


@dataclass
class TokenWindow:
    ref: TokenRef
    snapshots: list[dict[str, Any]]

    @property
    def latest(self) -> dict[str, Any]:
        return self.snapshots[-1]

    @property
    def history(self) -> list[dict[str, Any]]:
        """Everything before the newest measurement — the baseline."""
        return self.snapshots[:-1]

    @property
    def observed_at(self) -> datetime:
        return self.latest["observed_at"]

    @property
    def size(self) -> int:
        return len(self.snapshots)

    def series(self, field_name: str, *, history_only: bool = True) -> list[float]:
        rows = self.history if history_only else self.snapshots
        return [
            float(row[field_name])
            for row in rows
            if row.get(field_name) is not None
        ]

    def value(self, field_name: str) -> float | None:
        raw = self.latest.get(field_name)
        return None if raw is None else float(raw)

    def previous(self, field_name: str) -> float | None:
        if len(self.snapshots) < 2:
            return None
        raw = self.snapshots[-2].get(field_name)
        return None if raw is None else float(raw)

    def deltas(self, field_name: str) -> list[float]:
        """Successive differences across the baseline, for growth rates."""
        values = [
            float(row[field_name])
            for row in self.history
            if row.get(field_name) is not None
        ]
        return [later - earlier for earlier, later in pairwise(values)]

    def completeness(self) -> float:
        """Share of the expected fields present in the newest measurement.

        This is the basis of an observation's `confidence`: confidence in the
        measurement, not in any conclusion drawn from it.
        """
        present = sum(1 for name in SNAPSHOT_FIELDS if self.latest.get(name) is not None)
        return present / len(SNAPSHOT_FIELDS)


@dataclass
class SocialWindow:
    token_address: str | None
    posts: list[dict[str, Any]]
    window_end: datetime
    window_hours: int
    hourly_counts: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.hourly_counts:
            self.hourly_counts = self._bucket()

    def _bucket(self) -> list[int]:
        buckets = [0] * self.window_hours
        start = self.window_end - timedelta(hours=self.window_hours)
        for post in self.posts:
            posted_at = post["posted_at"]
            if posted_at <= start or posted_at > self.window_end:
                continue
            offset = int((self.window_end - posted_at).total_seconds() // 3600)
            index = self.window_hours - 1 - min(offset, self.window_hours - 1)
            buckets[index] += 1
        return buckets

    @property
    def latest_hour(self) -> int:
        return self.hourly_counts[-1] if self.hourly_counts else 0

    @property
    def baseline_hours(self) -> list[int]:
        return self.hourly_counts[:-1]

    @property
    def unique_accounts_latest_hour(self) -> int:
        start = self.window_end - timedelta(hours=1)
        return len(
            {
                post.get("account_external_id")
                for post in self.posts
                if start < post["posted_at"] <= self.window_end
            }
        )

    def term_counts(self, *, latest_hour_only: bool = False) -> Counter[str]:
        start = self.window_end - timedelta(hours=1 if latest_hour_only else self.window_hours)
        counter: Counter[str] = Counter()
        for post in self.posts:
            if not (start < post["posted_at"] <= self.window_end):
                continue
            counter.update(post.get("matched_terms") or [])
        return counter


def build_token_window(ref: TokenRef, snapshots: list[dict[str, Any]]) -> TokenWindow:
    return TokenWindow(ref=ref, snapshots=sorted(snapshots, key=lambda row: row["observed_at"]))


def build_social_window(
    posts: list[dict[str, Any]],
    *,
    window_end: datetime,
    window_hours: int,
    token_address: str | None = None,
) -> SocialWindow:
    return SocialWindow(
        token_address=token_address,
        posts=sorted(posts, key=lambda row: row["posted_at"]),
        window_end=window_end,
        window_hours=window_hours,
    )
