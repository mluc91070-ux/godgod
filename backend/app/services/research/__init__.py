"""Research engines (PHASE 4-6): hypothesis, experiment, critic.

Deterministic. Templates, thresholds and statistics — no model in the loop.
"""

from app.services.research.critic import (
    CHECK_NAMES,
    CRITIC_VERSION,
    CriticReview,
    hypothesis_status,
    review,
)
from app.services.research.cycle import (
    RESEARCH_RUN_NAME,
    ResearchReport,
    generate_hypotheses,
    run_experiment_for,
    run_research_cycle,
)
from app.services.research.dataset import (
    DATASET_VERSION,
    UNIT_OF_ANALYSIS,
    Dataset,
    build_dataset,
)
from app.services.research.experiments import MIN_CELL, ExperimentOutcome, evaluate
from app.services.research.templates import TEMPLATES, HypothesisTemplate

__all__ = [
    "CHECK_NAMES",
    "CRITIC_VERSION",
    "DATASET_VERSION",
    "MIN_CELL",
    "RESEARCH_RUN_NAME",
    "TEMPLATES",
    "UNIT_OF_ANALYSIS",
    "CriticReview",
    "Dataset",
    "ExperimentOutcome",
    "HypothesisTemplate",
    "ResearchReport",
    "build_dataset",
    "evaluate",
    "generate_hypotheses",
    "hypothesis_status",
    "review",
    "run_experiment_for",
    "run_research_cycle",
]
