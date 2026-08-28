"""Responses for the model-backed agents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BudgetOut(BaseModel):
    daily_budget_usd: float
    spent_today_usd: float
    remaining_usd: float
    unpriced_runs_today: int
    """Runs that recorded no cost. Any of these makes spend a floor, not a total."""
    priced: bool
    """False when the per-token prices are unset; then no model call is made."""


class WriterOut(BaseModel):
    ok: bool
    draft_id: str | None = None
    text: str | None = None
    """The text produced, kept even when it was refused, so the refusal is auditable."""
    reasons: list[str] = Field(default_factory=list)
    error: str | None = None
    run_id: str | None = None
    cost_usd: float | None = None
    """None means the cost is unknown, never that the call was free."""


class ReviewOut(BaseModel):
    verdict: str
    reasons: list[str] = Field(default_factory=list)
    model_verdict: str | None = None
    """None when no model read the draft. Not the same as an approval."""
    model_reason: str | None = None
    run_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None
    version: str


class CriticOut(BaseModel):
    verdict: str
    """The stricter of the deterministic and model verdicts, never the lighter."""
    deterministic_verdict: str
    model_verdict: str | None = None
    """None when no model read it. Not the same as a PASS."""
    objection: str | None = None
    dropped: list[str] = Field(default_factory=list)
    """Objections thrown away, and why — including a model verdict that tried
    to be lighter than the deterministic one."""
    run_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None
    version: str


class ObserverOut(BaseModel):
    ok: bool
    reading: str | None = None
    anomaly_id: str | None = None
    reasons: list[str] = Field(default_factory=list)
    run_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None
    version: str


class CollectionOut(BaseModel):
    queries: int
    fetched: int
    stored: int
    accounts_created: int
    dropped: dict[str, int] = Field(default_factory=dict)
    """Why a fetched post was not stored, by named reason."""
    rate_limited: bool
    """True when the quota stopped the run; `fetched` is then a floor."""
    reset_at: str | None = None
    error: str | None = None
    duration_ms: int
    complete: bool
    """False when the run was cut short. Zero posts with complete=false is not
    the same claim as zero posts with complete=true."""
    llm_calls: int = 0


class ChainOut(BaseModel):
    candidates: int
    measured: int
    tokens_created: int
    snapshots_stored: int
    distributions_measured: int
    """Tokens whose top-10 holder share the RPC could compute. The rest are null."""
    migrations_seen: int = 0
    """Completed bonding curves the launchpad reported this run."""
    migrations_measured: int = 0
    """Of those, the ones the market could actually measure. A gap means tokens
    that migrated but have no pair yet — a real state, counted in `dropped`."""
    launchpad_error: str | None = None
    """Named apart from `error`: one frame can fail while the other works."""
    dropped: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int
    complete: bool
    llm_calls: int = 0


class GoLiveOut(BaseModel):
    ready: bool
    """True when some token has enough measurements for the pipeline to observe."""
    deleted: bool
    demo_mode: bool
    """Still true until the environment is changed; deleting rows does not flip it."""
    live_tokens: int
    measurements_needed: int
    ready_tokens: list[str] = Field(default_factory=list)
    deepest: int
    """Most measurements held for any single token."""
    demo_tokens: int
    note: str
