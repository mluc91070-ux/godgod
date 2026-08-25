"""Agents, agent runs, system events and metric snapshots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONDict
from app.models.base import Entity


class Agent(Entity):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(256), nullable=False)
    question: Mapped[str] = mapped_column(String(256), nullable=False)
    """The single question this agent answers."""
    inputs: Mapped[list | None] = mapped_column(JSONDict)
    outputs: Mapped[list | None] = mapped_column(JSONDict)
    allowed_tools: Mapped[list | None] = mapped_column(JSONDict)
    model_role: Mapped[str | None] = mapped_column(String(32))
    """MODEL_FAST | MODEL_REASONING | MODEL_WRITER | MODEL_CRITIC"""
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    implemented: Mapped[bool] = mapped_column(default=False, nullable=False)
    """False until the agent actually runs. The UI must not imply otherwise."""

    runs: Mapped[list[AgentRun]] = relationship(back_populates="agent")


class AgentRun(Entity):
    __tablename__ = "agent_runs"

    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), index=True
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str | None] = mapped_column(String(128))
    input_summary: Mapped[str | None] = mapped_column(Text)
    output_summary: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="OK", nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    agent: Mapped[Agent | None] = relationship(back_populates="runs")


class SystemEvent(Entity):
    """Append-only event log. Feeds the live terminal."""

    __tablename__ = "system_events"

    seq: Mapped[int | None] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(36), index=True)
    detail: Mapped[dict | None] = mapped_column(JSONDict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class MetricsSnapshot(Entity):
    __tablename__ = "metrics_snapshots"

    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    window: Mapped[str] = mapped_column(String(16), default="daily", nullable=False, index=True)
    observations_count: Mapped[int | None] = mapped_column(Integer)
    anomalies_count: Mapped[int | None] = mapped_column(Integer)
    hypotheses_count: Mapped[int | None] = mapped_column(Integer)
    experiments_count: Mapped[int | None] = mapped_column(Integer)
    supported_count: Mapped[int | None] = mapped_column(Integer)
    rejected_count: Mapped[int | None] = mapped_column(Integer)
    inconclusive_count: Mapped[int | None] = mapped_column(Integer)
    memories_count: Mapped[int | None] = mapped_column(Integer)
    llm_cost_usd: Mapped[float | None] = mapped_column(Float)
    detail: Mapped[dict | None] = mapped_column(JSONDict)
