"""Model-backed agents.

Two exist today: the writer and the reviewer. The other four roles in the
roster — observer, researcher, data_scientist, critic — run as deterministic
engines under `app/services/`, and their agent rows keep `implemented=false`
because the agent does not exist even though the job gets done.

Every call goes through `run_agent`, which checks the budget first and records
the attempt whether it succeeds or fails.
"""

from app.agents.base import IMPLEMENTED_AGENTS, AgentOutcome, run_agent
from app.agents.guards import DraftCheck, check_draft, ungrounded_numbers
from app.agents.reviewer import REVIEWER_VERSION, ReviewOutcome, review_draft
from app.agents.writer import WRITER_SOURCE, WriterOutcome, write_draft_for_result

__all__ = [
    "IMPLEMENTED_AGENTS",
    "REVIEWER_VERSION",
    "WRITER_SOURCE",
    "AgentOutcome",
    "DraftCheck",
    "ReviewOutcome",
    "WriterOutcome",
    "check_draft",
    "review_draft",
    "run_agent",
    "ungrounded_numbers",
    "write_draft_for_result",
]
