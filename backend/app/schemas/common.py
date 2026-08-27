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


class ResearchInfo(BaseModel):
    """The hypothesis, experiment and critic engines."""

    implemented: bool
    hypothesis_templates: int
    critic_version: str
    critic_checks: list[str]
    min_group_size: int
    """Below this per group, a difference is reported but not judged."""
    unit_of_analysis: str
    llm_in_loop: bool
    last_run_at: datetime | None


class CollectionInfo(BaseModel):
    """What the live collectors have gathered, separate from the demo dataset.

    Shown even while DEMO_MODE is on, because the collectors run regardless and
    a visitor should be able to see that real measurement is happening — and how
    far it still is from being enough to research.
    """

    live_tokens: int
    tokens_promoted: int
    """Found by the promotion feed — tokens somebody paid to place."""
    tokens_migrated: int
    """Found by a completed bonding curve — nobody paid for placement.

    Two populations, kept apart because they are not the same one. A result
    that holds in one and not the other is a result about the sampling frame.
    """
    tokens_unrecorded_frame: int
    """Measured before the sampling frame was recorded at all.

    These are not promoted-by-default. The collector had one population when
    they were stored and did not write down which, so the honest value is
    "unrecorded" — not a label assigned retroactively to make three numbers
    add up.
    """
    migrations_available: bool
    """False when no launchpad is configured, so an empty migrated cohort is
    distinguishable from one nothing ever looked for."""
    live_snapshots: int
    live_posts: int
    deepest_history: int
    """Most measurements held for any single token."""
    needed_to_observe: int
    """Measurements one token needs before any detector can speak."""
    observing_live: bool
    """False while the pipeline still reads the fixture series."""
    last_chain_run_at: datetime | None
    last_x_run_at: datetime | None


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
    research: ResearchInfo
    collection: CollectionInfo
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
        description="True when GET /api/live/stream is available on this build.",
    )
