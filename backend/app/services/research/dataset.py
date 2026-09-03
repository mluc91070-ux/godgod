"""Dataset construction.

The unit of analysis is a **token-measurement**: one token at one reading, with
a full trailing window behind it and another reading a stated number of hours
ahead of it.

Three properties matter more than the numbers:

- **The hours are hours.** This module used to slice the series by position —
  `snapshots[index + horizon_hours]` — while every hypothesis it fed said
  "six hours later". Measurements land on a quarter-hour grid, so six positions
  was ninety minutes, and the site published a claim about a horizon it had
  never measured. Window and horizon are now spans of clock time, resolved
  against `observed_at`, and a row is dropped when no reading exists near the
  target rather than quietly standing in for one.
- **No look-ahead.** Exposure is computed from measurements at or before `t`;
  the outcome is read strictly at `t + horizon`. The rows carry both timestamps
  so this is checkable after the fact, and the critic does check it.
- **Reproducible.** Every dataset is hashed over its sorted rows, so an
  experiment can be re-run and compared byte for byte.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Token, TokenSnapshot
from app.models.base import as_utc
from app.providers.source import TokenRef
from app.services.chain import WATCHLIST
from app.services.observation.detectors import DetectorParams
from app.services.observation.windows import build_token_window
from app.services.research.templates import HypothesisTemplate

DATASET_VERSION = "token-measurements-v2"
"""Bumped from `token-hours-v1`: the rows mean something different now.

A v1 hash and a v2 hash over the same database are not comparable, because v1
counted positions where v2 counts hours. Leaving the version alone would have
made the two silently look like the same dataset.
"""

UNIT_OF_ANALYSIS = "token-measurement"

LIQUIDITY_STRATA: tuple[tuple[str, float, float], ...] = (
    ("micro", 0.0, 25_000.0),
    ("small", 25_000.0, 100_000.0),
    ("mid", 100_000.0, 1_000_000.0),
    ("large", 1_000_000.0, float("inf")),
)

AGE_STRATA: tuple[tuple[str, float, float], ...] = (
    ("new", 0.0, 6.0),
    ("young", 6.0, 48.0),
    ("established", 48.0, 336.0),
    ("old", 336.0, float("inf")),
)
"""Hours. A token minutes old and a token a month old are not the same
population, and a comparison that pools them is answering neither question."""


def stratum_for(liquidity: float | None) -> str:
    if liquidity is None:
        return "unknown"
    for name, low, high in LIQUIDITY_STRATA:
        if low <= liquidity < high:
            return name
    return "unknown"


def age_stratum_for(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "unknown"
    hours = age_seconds / 3600
    for name, low, high in AGE_STRATA:
        if low <= hours < high:
            return name
    return "unknown"


def horizon_tolerance(horizon_hours: float) -> timedelta:
    """How far past the target a reading may sit and still count as it.

    The grid is quarter-hourly and tokens do miss slots, so demanding an exact
    hit would empty the dataset. Ten percent of the horizon, never under half
    an hour, keeps the slack proportional to the claim being made.
    """
    return max(timedelta(minutes=30), timedelta(hours=horizon_hours * 0.1))


@dataclass
class DatasetRow:
    token_address: str
    symbol: str | None
    exposure_at: datetime
    outcome_at: datetime
    exposed: bool
    outcome: bool
    stratum: str
    age_hours: float | None

    def as_key(self) -> list[Any]:
        return [
            self.token_address,
            self.exposure_at.isoformat(),
            self.outcome_at.isoformat(),
            self.exposed,
            self.outcome,
            self.stratum,
        ]


@dataclass
class Dataset:
    template_key: str
    rows: list[DatasetRow] = field(default_factory=list)
    excluded: dict[str, int] = field(default_factory=dict)
    """Rows that could not be built, by reason. Never silently dropped."""
    period_start: datetime | None = None
    period_end: datetime | None = None

    def drop(self, reason: str) -> None:
        self.excluded[reason] = self.excluded.get(reason, 0) + 1

    @property
    def exposed(self) -> list[DatasetRow]:
        return [row for row in self.rows if row.exposed]

    @property
    def controls(self) -> list[DatasetRow]:
        return [row for row in self.rows if not row.exposed]

    @property
    def tokens(self) -> set[str]:
        return {row.token_address for row in self.rows}

    def hash(self) -> str:
        payload = json.dumps(
            sorted((row.as_key() for row in self.rows), key=lambda item: item[:3]),
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def split(self, fraction: float = 0.5) -> tuple[list[DatasetRow], list[DatasetRow]]:
        """Chronological split. Used for the stability check, never for tuning."""
        ordered = sorted(self.rows, key=lambda row: row.exposure_at)
        cut = int(len(ordered) * fraction)
        return ordered[:cut], ordered[cut:]


def _snapshot_dict(row: TokenSnapshot) -> dict[str, Any]:
    return {
        "observed_at": as_utc(row.observed_at),
        "market_cap_usd": row.market_cap_usd,
        "liquidity_usd": row.liquidity_usd,
        "volume_usd": row.volume_usd,
        "holders": row.holders,
        "holder_concentration_top10": row.holder_concentration_top10,
        "transactions": row.transactions,
        "buys": row.buys,
        "sells": row.sells,
        "age_seconds": row.age_seconds,
        "quote_kind": row.quote_kind,
        "quote_symbol": row.quote_symbol,
    }


def _reading_at(
    snapshots: list[dict[str, Any]], start: int, target: datetime, tolerance: timedelta
) -> dict[str, Any] | None:
    """The earliest reading at or after `target`, if one lands close enough.

    Scanning forward from `start` keeps this linear over the series: the caller
    walks exposure points in order, so the outcome it wants never moves back.
    """
    for row in snapshots[start:]:
        moment = row["observed_at"]
        if moment < target:
            continue
        return row if moment - target <= tolerance else None
    return None


async def build_dataset(
    session: AsyncSession,
    template: HypothesisTemplate,
    *,
    params: DetectorParams | None = None,
) -> Dataset:
    """Build the comparison table for one template, on its own timescale.

    The window and the horizon come from the template rather than from a global
    setting: a withdrawal is a question about the next half day, a buy-side
    shift a question about the next hour, and running both over one shared
    six-hour frame was most of what made six hypotheses read like one.
    """
    params = params or DetectorParams()
    dataset = Dataset(template_key=template.key)

    window = timedelta(hours=template.window_hours)
    horizon = timedelta(hours=template.horizon_hours)
    tolerance = horizon_tolerance(template.horizon_hours)

    tokens = (await session.scalars(select(Token))).all()
    for token in tokens:
        if token.source == WATCHLIST:
            # Hand-named tokens are measured and shown, never compared. The
            # list was written after seeing which ones did well, so every row
            # in it is a survivor and any rate computed over them is a fact
            # about the person who wrote the list.
            dataset.drop("hand_selected_token")
            continue
        snapshots = [
            _snapshot_dict(row)
            for row in (
                await session.scalars(
                    select(TokenSnapshot)
                    .where(TokenSnapshot.token_id == token.id)
                    .order_by(TokenSnapshot.observed_at)
                )
            ).all()
        ]
        if len(snapshots) < 2:
            dataset.drop("token_series_too_short")
            continue

        span = snapshots[-1]["observed_at"] - snapshots[0]["observed_at"]
        if span < window + horizon:
            # Not yet watched long enough to hold one exposure and its outcome.
            dataset.drop("token_series_too_short")
            continue

        ref = TokenRef(
            address=token.address,
            symbol=token.symbol,
            name=token.name,
            decimals=token.decimals,
            launch_time=token.launch_time,
            launchpad=token.launchpad,
        )

        first = snapshots[0]["observed_at"]
        for index, current in enumerate(snapshots):
            moment = current["observed_at"]
            if moment - first < window:
                # No full window behind this reading yet.
                continue

            trailing = [
                row for row in snapshots[: index + 1] if row["observed_at"] >= moment - window
            ]
            if len(trailing) < template.min_window_points:
                dataset.drop("window_too_sparse")
                continue

            later = _reading_at(snapshots, index + 1, moment + horizon, tolerance)
            if later is None:
                dataset.drop("no_reading_at_horizon")
                continue

            if not template.eligible(current):
                # Not exposed *and* not a valid control. A template that
                # compares two named groups has to be able to say a row is
                # neither, or everything it did not select becomes its
                # baseline: rows whose quote asset was never recorded would
                # sit in the control arm as though the system had checked
                # them and found nothing. Silence is not a comparison group.
                dataset.drop("outside_template_population")
                continue

            result = template.outcome(current, later)
            if result is None:
                dataset.drop("outcome_unmeasurable")
                continue

            age_seconds = current.get("age_seconds")
            if template.stratify_by == "age":
                band = age_stratum_for(age_seconds)
            elif template.stratify_by == "frame":
                band = token.source or "unrecorded"
            else:
                band = stratum_for(current.get("liquidity_usd"))

            # The chain leads every stratum, so no comparison is ever held
            # across two of them. This is not a refinement of the existing
            # bands: it is what stops the population from being pooled the
            # moment MARKET_CHAINS names a second network. A token whose row
            # predates that column reads "solana", which is what it was.
            stratum = f"{token.chain or 'unrecorded'}/{band}"

            dataset.rows.append(
                DatasetRow(
                    token_address=token.address,
                    symbol=token.symbol,
                    exposure_at=moment,
                    outcome_at=later["observed_at"],
                    exposed=bool(template.trigger(build_token_window(ref, trailing), params)),
                    outcome=bool(result),
                    stratum=stratum,
                    age_hours=None if age_seconds is None else round(age_seconds / 3600, 2),
                )
            )

    if dataset.rows:
        dataset.period_start = min(row.exposure_at for row in dataset.rows)
        dataset.period_end = max(row.outcome_at for row in dataset.rows)
    return dataset
