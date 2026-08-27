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

    # --- chain and market (PHASE 8) ------------------------------------
    solana_timeout_seconds: float = 20.0

    solana_retry_seconds: float = 1.5
    """Backoff before one retry of a rate-limited call. Zero disables it.

    Measured against the shared public endpoint: `getTokenSupply` answers,
    `getTokenLargestAccounts` throttles. One retry is worth trying; more would
    be pretending a shared endpoint is a dedicated one.
    """

    market_api_url: str | None = None
    """Where liquidity, volume and trade counts are read from.

    A URL rather than a vendor name, for the same reason SOLANA_RPC_URL is:
    swapping data sources must be an environment change, not a code change.
    """

    market_timeout_seconds: float = 20.0

    chain_watch_queries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["solana"]
    )
    """Search terms the collector uses to find tokens worth measuring."""

    chain_max_tokens: int = 40
    """Tokens tracked per collection run. The deterministic floors drop most of
    them before anything is stored; this caps the work before that."""

    chain_min_liquidity_usd: float = 10_000.0
    """A token below this is not worth a row. Distinct from the pipeline's own
    floor, which decides what is worth *observing* once it is stored."""

    chain_min_volume_usd: float = 25_000.0
    """Liquidity alone says nothing.

    Measured on the live feed: pools holding over a billion dollars of wrapped
    SOL reported about a hundred dollars of daily volume. That is a parked
    balance, not a market, and tracking it would fill the dataset with tokens
    nothing ever happens to.
    """

    launchpad_api_url: str | None = None
    """Where completed bonding curves are read from.

    A URL rather than a vendor name, same rule as SOLANA_RPC_URL and
    MARKET_API_URL. Unset means migrations are unavailable and every token
    keeps `bonding_curve_state` NULL — never "unmigrated" by default.
    """

    launchpad_timeout_seconds: float = 20.0

    launchpad_migrations: bool = True
    """Add recently migrated tokens to each collection run.

    A second sampling frame, and deliberately a different one: the promotion
    feed is tokens somebody paid to show, this is tokens that filled a curve.
    Every token records which frame found it, because a result that holds in
    one and not the other is a result about the frame, not about the market.
    """

    launchpad_max_tokens: int = 25
    """Migrations added per run, on top of the promotion feed. Capped because
    the market API is then asked to measure each of them."""

    launchpad_min_liquidity_usd: float = 1_000.0
    """A far lower floor than the promotion feed's, and deliberately so.

    The $10k floor exists to reject a parked balance: a deep pool nobody
    trades. A token that migrated twenty minutes ago cannot be a parked
    balance, and applying the same floor to it rejects the opposite thing.
    Measured on a live run: of 25 fresh migrations, the $10k floor dropped 21
    — including one 18 minutes old doing $343k of volume on a $6k pool, which
    is precisely the event this system exists to study.

    This floor only rejects a pool with nothing left in it.
    """

    launchpad_min_volume_usd: float = 25_000.0
    """Same question as the promotion feed's floor — is anything happening —
    and the same answer, so the same number. On a token under an hour old the
    24h figure is simply everything that has traded since it launched."""

    chain_discover: bool = True
    """Read the promotion feed instead of searching by name.

    Name search on a permissionless chain returns clones of whatever was typed.
    The promotion feed is a real sampling frame — of tokens someone is pushing,
    which is exactly the population this system studies, and which every
    experiment records as its population rather than pretending it is neutral.
    """

    # --- X (PHASE 7) ---------------------------------------------------
    x_timeout_seconds: float = 30.0

    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_token_secret: str | None = None
    """Posting needs user context; the bearer token can only read.

    A deployment can hold a valid X_BEARER_TOKEN, on a paid tier, and still be
    unable to publish a single post. These four are what writing requires.
    """

    x_min_minutes_between_posts: int = 45
    """Floor between two published posts.

    A research system that posts whenever it finishes a cycle is a bot, and it
    exhausts a 500-post month in under a week."""

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

    @field_validator("cors_origins", "x_search_terms", "chain_watch_queries", mode="before")
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
