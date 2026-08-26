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
