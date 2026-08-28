"""Model-backed agents.

Four exist: the writer, the reviewer, the critic and the observer. Each is
constrained rather than trusted — the reviewer and the critic can only make a
verdict harsher, and the observer reads an anomaly a detector already fired
rather than finding one.

The researcher and the data_scientist stay deterministic engines under
`app/services/` and their agent rows keep `implemented=false`. That is a design
decision, not a backlog item: a hypothesis comes from a template so that no
model sees the data before deciding what to claim about it, and the statistics
have one right answer.

Every call goes through `run_agent`, which checks the budget first and records
the attempt whether it succeeds or fails.
"""

from app.agents.base import IMPLEMENTED_AGENTS, AgentOutcome, run_agent
from app.agents.critic import (
    CRITIC_AGENT_VERSION,
    CriticOutcome,
    critique_result,
)
from app.agents.guards import DraftCheck, check_draft, ungrounded_numbers
from app.agents.observer import OBSERVER_VERSION, ObserverOutcome, read_anomaly
from app.agents.reviewer import REVIEWER_VERSION, ReviewOutcome, review_draft
from app.agents.writer import WRITER_SOURCE, WriterOutcome, write_draft_for_result

__all__ = [
    "CRITIC_AGENT_VERSION",
    "IMPLEMENTED_AGENTS",
    "OBSERVER_VERSION",
    "REVIEWER_VERSION",
    "WRITER_SOURCE",
    "AgentOutcome",
    "CriticOutcome",
    "DraftCheck",
    "ObserverOutcome",
    "ReviewOutcome",
    "WriterOutcome",
    "check_draft",
    "critique_result",
    "read_anomaly",
    "review_draft",
    "run_agent",
    "ungrounded_numbers",
    "write_draft_for_result",
]
