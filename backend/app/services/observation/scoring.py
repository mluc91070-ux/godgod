"""Novelty, importance and confidence.

All three are deterministic. They decide what is worth storing and, later,
what is worth reasoning about — so they must be explainable in one sentence
each:

    novelty     how unlike the recent record this is
    importance  how much it matters if it is real
    confidence  how complete the measurement was
"""

from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Observation
from app.services.embeddings import EmbeddingProvider, cosine, get_embedding_provider
from app.services.observation.windows import TokenWindow

RECENT_OBSERVATIONS = 25


async def novelty_score(
    session: AsyncSession,
    signature: str,
    *,
    kind: str | None = None,
    provider: EmbeddingProvider | None = None,
    limit: int = RECENT_OBSERVATIONS,
) -> float:
    """1.0 when nothing like this has been recorded, 0.0 when it is a repeat.

    Reuses the memory embedder, so "unlike" means unlike in wording — which
    is enough to suppress the same anomaly restated hour after hour, and is
    not claimed to be more than that.
    """
    provider = provider or get_embedding_provider()

    stmt = select(Observation).order_by(Observation.observed_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(Observation.kind == kind)
    recent = (await session.scalars(stmt)).all()
    if not recent:
        return 1.0

    vector = provider.embed(signature)
    closest = max(
        (cosine(vector, provider.embed(row.summary)) for row in recent),
        default=0.0,
    )
    return round(max(0.0, min(1.0, 1.0 - closest)), 4)


def scale_factor(liquidity_usd: float | None) -> float:
    """Bounded log scale: $1k → 0.5, $1m → 1.0, unknown → 0.

    Unknown is 0 rather than a middling default: a subject whose size we did
    not measure does not get credit for being big.
    """
    if not liquidity_usd or liquidity_usd <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log10(1.0 + liquidity_usd) / 6.0))


def importance_score(anomaly_scores: list[float], liquidity_usd: float | None) -> float:
    """How much this matters: mostly the anomaly, partly the size at stake."""
    strongest = max(anomaly_scores) if anomaly_scores else 0.0
    return round(0.6 * strongest + 0.4 * scale_factor(liquidity_usd), 4)


def confidence_score(window: TokenWindow) -> float:
    """Completeness of the measurement, not belief in a conclusion."""
    return round(window.completeness(), 4)
