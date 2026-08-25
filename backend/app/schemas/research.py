"""Read schemas for the research chain."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class AnomalyOut(ORMModel):
    id: str
    observation_id: str | None
    anomaly_type: str
    detector: str
    score: float | None
    baseline: dict | None
    measured: dict | None
    detected_at: datetime
    is_demo: bool


class ObservationOut(ORMModel):
    id: str
    seq: int | None
    kind: str
    summary: str
    subject_type: str | None
    subject_ref: str | None
    payload: dict | None
    novelty_score: float | None
    importance: float | None
    confidence: float | None
    observed_at: datetime
    source: str | None
    llm_reviewed: bool
    is_demo: bool


class ObservationDetail(ObservationOut):
    anomalies: list[AnomalyOut] = Field(default_factory=list)


class HypothesisOut(ORMModel):
    id: str
    seq: int | None
    statement: str
    question: str
    variables: dict | None
    population: str
    sample_definition: str
    timeframe: str
    baseline: str
    expected_result: str
    falsification_condition: str
    confidence: float | None
    status: str
    origin_observation_id: str | None
    created_at: datetime
    is_demo: bool


class ExperimentResultOut(ORMModel):
    id: str
    experiment_id: str
    outcome: str
    summary: str
    metrics: dict | None
    effect_size: float | None
    p_value: float | None
    confidence: float | None
    critic_verdict: str | None
    critic_notes: str | None
    critic_checks: dict | None
    limitations: str | None
    created_at: datetime
    is_demo: bool


class ExperimentOut(ORMModel):
    id: str
    seq: int | None
    hypothesis_id: str
    title: str
    method: str
    features: list | None
    parameters: dict | None
    dataset_version: str
    dataset_hash: str
    sample_size: int | None
    train_period: str | None
    validation_period: str | None
    out_of_sample_period: str | None
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    limitations: str | None
    is_demo: bool


class ExperimentDetail(ExperimentOut):
    results: list[ExperimentResultOut] = Field(default_factory=list)
    hypothesis: HypothesisOut | None = None


class HypothesisDetail(HypothesisOut):
    experiments: list[ExperimentOut] = Field(default_factory=list)


class TraceStepOut(ORMModel):
    id: str
    position: int
    kind: str
    summary: str
    ref_type: str | None
    ref_id: str | None
    occurred_at: datetime | None
    detail: dict | None


class TraceOut(ORMModel):
    id: str
    seq: int | None
    title: str | None
    hypothesis_id: str | None
    experiment_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[TraceStepOut] = Field(default_factory=list)
    is_demo: bool


class PatternOut(ORMModel):
    id: str
    name: str
    description: str
    status: str
    support_count: int
    contradiction_count: int
    confidence: float | None
    first_seen_at: datetime | None
    last_confirmed_at: datetime | None
    evidence_refs: list | None
    is_demo: bool


class MemoryOut(ORMModel):
    id: str
    memory_type: str
    content: str
    summary: str | None
    meta: dict | None
    source: str | None
    confidence: float | None
    ref_type: str | None
    ref_id: str | None
    created_at: datetime
    is_demo: bool


class MemorySearchResponse(ORMModel):
    query: str
    method: str
    """PHASE 1 is lexical only. Vector search arrives in PHASE 2."""
    semantic: bool
    items: list[MemoryOut]
    total: int
    is_demo: bool


class SourceOut(ORMModel):
    id: str
    kind: str
    name: str
    url: str | None
    description: str | None
    reliability: float | None
    last_used_at: datetime | None
    is_demo: bool


class EventOut(ORMModel):
    id: str
    seq: int | None
    event_type: str
    message: str
    level: str
    ref_type: str | None
    ref_id: str | None
    detail: dict | None
    occurred_at: datetime
    is_demo: bool


class AgentOut(ORMModel):
    id: str
    name: str
    role: str
    question: str
    inputs: list | None
    outputs: list | None
    allowed_tools: list | None
    model_role: str | None
    enabled: bool
    implemented: bool


class AgentRunOut(ORMModel):
    id: str
    agent_name: str
    model: str | None
    input_summary: str | None
    output_summary: str | None
    duration_ms: int | None
    status: str
    error: str | None
    estimated_cost_usd: float | None
    started_at: datetime | None
    is_demo: bool


class MetricsResponse(ORMModel):
    window: str
    captured_at: datetime | None
    counts: dict
    llm_cost_usd: float | None
    is_demo: bool
