"""Model registry.

Importing this package is what populates ``Base.metadata`` — Alembic and the
test harness both rely on it.
"""

from app.models.base import Base, Entity, new_id, utcnow
from app.models.memory import Memory
from app.models.onchain import (
    ChainCursor,
    LaunchpadLaunch,
    Token,
    TokenSnapshot,
    Wallet,
    WalletCluster,
)
from app.models.research import (
    Anomaly,
    Experiment,
    ExperimentResult,
    Hypothesis,
    Observation,
    Pattern,
    ResearchSource,
    ResearchTrace,
    TraceStep,
)
from app.models.social import ContentDraft, PublishedPost, SocialAccount, SocialPost
from app.models.system import Agent, AgentRun, MetricsSnapshot, SystemEvent

__all__ = [
    "Agent",
    "AgentRun",
    "Anomaly",
    "Base",
    "ChainCursor",
    "ContentDraft",
    "Entity",
    "Experiment",
    "ExperimentResult",
    "Hypothesis",
    "LaunchpadLaunch",
    "Memory",
    "MetricsSnapshot",
    "Observation",
    "Pattern",
    "PublishedPost",
    "ResearchSource",
    "ResearchTrace",
    "SocialAccount",
    "SocialPost",
    "SystemEvent",
    "Token",
    "TokenSnapshot",
    "TraceStep",
    "Wallet",
    "WalletCluster",
    "new_id",
    "utcnow",
]
