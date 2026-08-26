"""Dataset construction.

The unit of analysis is a **token-hour**: one token at one measurement, with a
full trailing window behind it and a measurement `horizon_hours` ahead of it.

Two properties matter more than the numbers:

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
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Token, TokenSnapshot
from app.models.base import as_utc
from app.providers.source import TokenRef
from app.services.observation.detectors import DetectorParams
from app.services.observation.windows import build_token_window
from app.services.research.templates import HypothesisTemplate

DATASET_VERSION = "token-hours-v1"

LIQUIDITY_STRATA: tuple[tuple[str, float, float], ...] = (
    ("micro", 0.0, 25_000.0),
    ("small", 25_000.0, 100_000.0),
    ("mid", 100_000.0, 1_000_000.0),
    ("large", 1_000_000.0, float("inf")),
)


def stratum_for(liquidity: float | None) -> str:
    if liquidity is None:
        return "unknown"
    for name, low, high in LIQUIDITY_STRATA:
        if low <= liquidity < high:
            return name
    return "unknown"


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
    }


async def build_dataset(
    session: AsyncSession,
    template: HypothesisTemplate,
    *,
    window_hours: int = 6,
    params: DetectorParams | None = None,
) -> Dataset:
    params = params or DetectorParams()
    dataset = Dataset(template_key=template.key)

    tokens = (await session.scalars(select(Token))).all()
    for token in tokens:
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
        if len(snapshots) < window_hours + 1 + template.horizon_hours:
            dataset.excluded["token_series_too_short"] = (
                dataset.excluded.get("token_series_too_short", 0) + 1
            )
            continue

        ref = TokenRef(
            address=token.address,
            symbol=token.symbol,
            name=token.name,
            decimals=token.decimals,
            launch_time=token.launch_time,
            launchpad=token.launchpad,
        )

        for index in range(window_hours, len(snapshots) - template.horizon_hours):
            window = build_token_window(ref, snapshots[index - window_hours : index + 1])
            current = snapshots[index]
            later = snapshots[index + template.horizon_hours]

            outcome = template.outcome(current, later)
            if outcome is None:
                dataset.excluded["outcome_unmeasurable"] = (
                    dataset.excluded.get("outcome_unmeasurable", 0) + 1
                )
                continue

            age_seconds = current.get("age_seconds")
            dataset.rows.append(
                DatasetRow(
                    token_address=token.address,
                    symbol=token.symbol,
                    exposure_at=current["observed_at"],
                    outcome_at=later["observed_at"],
                    exposed=bool(template.trigger(window, params)),
                    outcome=bool(outcome),
                    stratum=stratum_for(current.get("liquidity_usd")),
                    age_hours=None if age_seconds is None else round(age_seconds / 3600, 2),
                )
            )

    if dataset.rows:
        dataset.period_start = min(row.exposure_at for row in dataset.rows)
        dataset.period_end = max(row.outcome_at for row in dataset.rows)
    return dataset
