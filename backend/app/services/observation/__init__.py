"""Observation engine (PHASE 3).

Deterministic end to end: no model is called, and every observation it writes
carries ``llm_reviewed=False``.
"""

from app.services.observation.detectors import AnomalyCandidate, DetectorParams
from app.services.observation.pipeline import ObservationPipeline, RunReport, run_backfill
from app.services.observation.scoring import (
    confidence_score,
    importance_score,
    novelty_score,
)
from app.services.observation.windows import (
    SocialWindow,
    TokenWindow,
    build_social_window,
    build_token_window,
)

__all__ = [
    "AnomalyCandidate",
    "DetectorParams",
    "ObservationPipeline",
    "RunReport",
    "SocialWindow",
    "TokenWindow",
    "build_social_window",
    "build_token_window",
    "confidence_score",
    "importance_score",
    "novelty_score",
    "run_backfill",
]
