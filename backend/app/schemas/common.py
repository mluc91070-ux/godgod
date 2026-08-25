"""Shared response envelopes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
    is_demo: bool = Field(
        description="True when every item in this page is fixture data."
    )


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    """"ok" or an error string. Never optimistic."""


class ModeInfo(BaseModel):
    demo_mode: bool
    autonomy_level: int
    autonomy_label: str
    x_mode: str
    wallet_execution_enabled: bool
    external_content_is_untrusted: bool


class ProviderStatus(BaseModel):
    name: str
    configured: bool
    implemented: bool
    note: str | None = None


class MemoryInfo(BaseModel):
    """What the memory subsystem can actually do right now."""

    embedding_provider: str
    embedding_model: str | None
    embedding_dim: int
    vector_search: bool
    semantic: bool
    backend: str
    """"pgvector" or "python-scan" — how ranking is performed."""


class PipelineInfo(BaseModel):
    """The observation stage: what it reads and whether a model is in the loop."""

    implemented: bool
    source: str
    source_is_demo: bool
    window_hours: int
    detectors: list[str]
    llm_in_loop: bool
    """False in PHASE 3. Every observation carries llm_reviewed=False."""
    last_run_at: datetime | None


class CountsInfo(BaseModel):
    observations: int
    anomalies: int
    hypotheses: int
    experiments: int
    results: int
    patterns: int
    memories: int
    drafts: int
    events: int


class StatusResponse(BaseModel):
    name: str
    version: str
    environment: str
    phase: str
    state: str
    mode: ModeInfo
    memory: MemoryInfo
    pipeline: PipelineInfo
    providers: list[ProviderStatus]
    counts: CountsInfo
    server_time: datetime


class LiveResponse(BaseModel):
    """Snapshot for the homepage. Reflects stored state only."""

    state: str
    is_demo: bool
    updated_at: datetime
    current_observation: dict | None
    current_hypothesis: dict | None
    current_experiment: dict | None
    last_event: dict | None
    activity: float = Field(ge=0.0, le=1.0)
    novelty: float | None = None
    confidence: float | None = None
    streaming: bool = Field(
        default=False,
        description="SSE streaming is a PHASE 9 deliverable; false until then.",
    )
