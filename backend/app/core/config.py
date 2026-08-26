"""Runtime configuration for GODGOD.

Everything is environment driven. No secret and no model name is ever
hard-coded anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AutonomyLevel = Literal[0, 1, 2, 3, 4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- identity -----------------------------------------------------
    app_name: str = "GODGOD"
    app_version: str = "0.1.0"
    environment: Literal["local", "staging", "production"] = "local"

    # --- modes --------------------------------------------------------
    demo_mode: bool = True
    """When true the API only serves clearly marked fixture data."""

    autonomy_level: int = 1
    """0 read-only, 1 research+draft (default), 2 approval+publish, 3 limited auto, 4 future."""

    x_mode: Literal["draft", "approval", "publish"] = "draft"
    """V1 never publishes automatically."""

    external_content_is_untrusted: bool = True
    """External social/on-chain text is DATA, never an instruction."""

    # --- database -----------------------------------------------------
    database_url: str = "sqlite+pysqlite:///./godgod.db"
    database_echo: bool = False

    # --- data ---------------------------------------------------------
    fixtures_dir: str | None = None
    """Defaults to <repo>/data/fixtures when unset."""

    # --- providers (unset in demo mode) -------------------------------
    solana_rpc_url: str | None = None
    solana_ws_url: str | None = None
    x_bearer_token: str | None = None
    anthropic_api_key: str | None = None

    # --- model routing (never hard-code model names elsewhere) --------
    model_fast: str | None = None
    model_reasoning: str | None = None
    model_writer: str | None = None
    model_critic: str | None = None

    # --- memory (PHASE 2) ---------------------------------------------
    embedding_provider: Literal["local", "none"] = "local"
    """"local" is a deterministic hashing embedder that needs no API key.
    A learned model becomes available when the provider work lands."""

    embedding_model: str = "local-hashing-v1"
    """Recorded on every stored vector. A vector whose model is unknown is
    a vector nobody can reproduce."""

    embedding_dim: int = 1536
    memory_scan_limit: int = 5000
    """Rows loaded by the Python cosine fallback used when the database is
    not PostgreSQL. PostgreSQL ranks with pgvector instead."""

    memory_similarity_threshold: float = 0.12
    """Minimum cosine for a hit to be returned.

    Measured on the demo corpus with the local hashing embedder: unrelated
    queries top out around 0.06 (hash collisions), while the weakest genuine
    match scores about 0.15. 0.12 sits between the two. Re-measure this when
    the embedder changes — it is a property of the embedder, not a taste.
    """

    # --- observation pipeline (PHASE 3) -------------------------------
    observation_window_hours: int = 6
    """Trailing window each detector compares its latest measurement against."""

    observation_min_snapshots: int = 6
    observation_min_liquidity_usd: float = 5_000.0
    observation_min_holders: int = 50
    """Deterministic floors. A subject below them is dropped before any
    scoring — this is the cheap gate that keeps model cost bounded."""

    observation_novelty_floor: float = 0.55
    """A candidate with no anomaly is only recorded if it is this novel."""

    observation_memory_importance_floor: float = 0.5
    """Below this, an observation is stored but not written to memory."""

    observation_cooldown_minutes: int = 180
    """Same subject + same anomaly type inside this window is a duplicate."""

    # --- live stream (PHASE 9) ----------------------------------------
    stream_poll_seconds: float = 1.0
    """How often the SSE endpoint looks for rows newer than the cursor.

    Polling, not a message bus: the writers are the pipeline and the research
    cycle, both of which commit to the same database the reader is watching.
    A queue would be a second source of truth for no gain at this scale.
    """

    stream_replay_events: int = 60
    """Events sent on connect so a new tab is not staring at an empty log."""

    stream_heartbeat_seconds: float = 15.0
    """Comment frame keeping proxies from closing an idle connection."""

    stream_max_seconds: float = 900.0
    """Hard lifetime for one connection. The client reconnects with its cursor;
    a forgotten tab does not poll the database forever."""

    # --- X (PHASE 7) ---------------------------------------------------
    x_timeout_seconds: float = 30.0

    x_search_terms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["solana meme coin", "pump.fun"]
    )
    """Comma-separated search queries the collector runs.

    Deliberately narrow: the recent-search quota is the binding constraint on
    every paid tier, so a broad query buys noise with the budget that a specific
    one spends on signal.
    """

    x_max_posts_per_run: int = 100
    """Ceiling per collection run. The quota is monthly; a runaway loop that
    spends it in an afternoon leaves the system blind for four weeks."""

    x_min_likes: int = 0
    x_exclude_reposts: bool = True
    """A repost is amplification, not an independent observation. Counting them
    as separate posts is how a single account looks like a movement."""

    # --- model calls --------------------------------------------------
    model_timeout_seconds: float = 60.0

    model_price_input_usd_per_mtok: float | None = None
    model_price_output_usd_per_mtok: float | None = None
    """Per-million-token prices for the configured models.

    Unset means unpriced, and an unpriced call records `estimated_cost_usd=None`
    rather than 0.0 — a fabricated zero would defeat the budget it is meant to
    protect. The budget guard refuses to spend what it cannot measure, so these
    must be set alongside the MODEL_* roles before any agent runs.
    """

    # --- cost control -------------------------------------------------
    llm_daily_budget_usd: float = 3.0
    memory_retrieval_limit: int = 20

    # --- api ----------------------------------------------------------
    api_prefix: str = "/api"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    """Comma-separated in the environment.

    NoDecode is load-bearing: without it pydantic-settings JSON-decodes a list
    field before any validator runs, and `CORS_ORIGINS=https://site.example`
    crashes the process at startup instead of being read as one origin.
    """
    admin_token: str | None = None

    @field_validator("autonomy_level")
    @classmethod
    def _check_autonomy(cls, v: int) -> int:
        if v not in (0, 1, 2, 3, 4):
            raise ValueError("autonomy_level must be between 0 and 4")
        return v

    @field_validator("cors_origins", "x_search_terms", mode="before")
    @classmethod
    def _split_list(cls, v: object) -> object:
        """Comma-separated in the environment; a list everywhere else."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def wallet_execution_enabled(self) -> bool:
        """V1 has no wallet execution path at all. Kept explicit for auditability."""
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
