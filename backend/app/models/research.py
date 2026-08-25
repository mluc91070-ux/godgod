"""The research chain: observation, anomaly, hypothesis, experiment, result,
pattern, source, and the immutable trace that ties them together.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONDict
from app.models.base import Entity


class Observation(Entity):
    __tablename__ = "observations"

    seq: Mapped[int | None] = mapped_column(Integer, index=True)
    """Public sequence number, e.g. "observation #041"."""
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String(32))
    subject_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    """Token address, wallet address or social id. Always a string."""

    payload: Mapped[dict | None] = mapped_column(JSONDict)
    """Normalized measurements. Absent measurements stay absent."""

    novelty_score: Mapped[float | None] = mapped_column(Float, index=True)
    importance: Mapped[float | None] = mapped_column(Float, index=True)
    confidence: Mapped[float | None] = mapped_column(Float)

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    source: Mapped[str | None] = mapped_column(String(128))
    llm_reviewed: Mapped[bool] = mapped_column(default=False, nullable=False)
    """False means deterministic filtering only — no model was ever called."""

    anomalies: Mapped[list[Anomaly]] = relationship(back_populates="observation")


class Anomaly(Entity):
    __tablename__ = "anomalies"

    observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("observations.id", ondelete="SET NULL"), index=True
    )
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    detector: Mapped[str] = mapped_column(String(128), nullable=False)
    """Name+version of the deterministic detector that fired."""
    score: Mapped[float | None] = mapped_column(Float, index=True)
    baseline: Mapped[dict | None] = mapped_column(JSONDict)
    measured: Mapped[dict | None] = mapped_column(JSONDict)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    observation: Mapped[Observation | None] = relationship(back_populates="anomalies")


class Hypothesis(Entity):
    __tablename__ = "hypotheses"

    seq: Mapped[int | None] = mapped_column(Integer, index=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[dict | None] = mapped_column(JSONDict)
    population: Mapped[str] = mapped_column(Text, nullable=False)
    sample_definition: Mapped[str] = mapped_column(Text, nullable=False)
    timeframe: Mapped[str] = mapped_column(String(256), nullable=False)
    baseline: Mapped[str] = mapped_column(Text, nullable=False)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    falsification_condition: Mapped[str] = mapped_column(Text, nullable=False)
    """A hypothesis without a falsification condition is not a hypothesis."""

    confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED", nullable=False, index=True)
    origin_observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("observations.id", ondelete="SET NULL"), index=True
    )

    experiments: Mapped[list[Experiment]] = relationship(back_populates="hypothesis")


class Experiment(Entity):
    __tablename__ = "experiments"

    seq: Mapped[int | None] = mapped_column(Integer, index=True)
    hypothesis_id: Mapped[str] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    features: Mapped[list | None] = mapped_column(JSONDict)
    parameters: Mapped[dict | None] = mapped_column(JSONDict)

    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    """Content hash of the exact dataset used. Reproducibility depends on it."""
    sample_size: Mapped[int | None] = mapped_column(Integer)
    train_period: Mapped[str | None] = mapped_column(String(128))
    validation_period: Mapped[str | None] = mapped_column(String(128))
    out_of_sample_period: Mapped[str | None] = mapped_column(String(128))

    status: Mapped[str] = mapped_column(String(32), default="PLANNED", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    limitations: Mapped[str | None] = mapped_column(Text)

    hypothesis: Mapped[Hypothesis] = relationship(back_populates="experiments")
    results: Mapped[list[ExperimentResult]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan"
    )


class ExperimentResult(Entity):
    __tablename__ = "experiment_results"

    experiment_id: Mapped[str] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), index=True
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """SUPPORTED | REJECTED | INCONCLUSIVE — inconclusive is a real result."""
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict | None] = mapped_column(JSONDict)
    effect_size: Mapped[float | None] = mapped_column(Float)
    p_value: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)

    critic_verdict: Mapped[str | None] = mapped_column(String(32), index=True)
    critic_notes: Mapped[str | None] = mapped_column(Text)
    critic_checks: Mapped[dict | None] = mapped_column(JSONDict)
    """Per-check outcomes: sample size, leakage, overfitting, confounders..."""

    limitations: Mapped[str | None] = mapped_column(Text)

    experiment: Mapped[Experiment] = relationship(back_populates="results")


class Pattern(Entity):
    __tablename__ = "patterns"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="CANDIDATE", nullable=False, index=True)
    """CANDIDATE | CONFIRMED | REJECTED | RETIRED"""
    support_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contradiction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_refs: Mapped[list | None] = mapped_column(JSONDict)


class ResearchSource(Entity):
    """Where a fact came from. Cited, never invented."""

    __tablename__ = "research_sources"

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    """RPC | API | DATASET | FIXTURE | MANUAL"""
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    reliability: Mapped[float | None] = mapped_column(Float)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResearchTrace(Entity):
    """Immutable record of one research cycle."""

    __tablename__ = "research_traces"

    seq: Mapped[int | None] = mapped_column(Integer, index=True)
    title: Mapped[str | None] = mapped_column(String(512))
    hypothesis_id: Mapped[str | None] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="SET NULL"), index=True
    )
    experiment_id: Mapped[str | None] = mapped_column(
        ForeignKey("experiments.id", ondelete="SET NULL"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list[TraceStep]] = relationship(
        back_populates="trace",
        cascade="all, delete-orphan",
        order_by="TraceStep.position",
    )


class TraceStep(Entity):
    __tablename__ = "trace_steps"

    trace_id: Mapped[str] = mapped_column(
        ForeignKey("research_traces.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(36))
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[dict | None] = mapped_column(JSONDict)

    trace: Mapped[ResearchTrace] = relationship(back_populates="steps")
