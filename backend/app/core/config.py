"""Runtime configuration for GODGOD.

Everything is environment driven. No secret and no model name is ever
hard-coded anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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

    # --- cost control -------------------------------------------------
    llm_daily_budget_usd: float = 3.0
    memory_retrieval_limit: int = 20

    # --- api ----------------------------------------------------------
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    admin_token: str | None = None

    @field_validator("autonomy_level")
    @classmethod
    def _check_autonomy(cls, v: int) -> int:
        if v not in (0, 1, 2, 3, 4):
            raise ValueError("autonomy_level must be between 0 and 4")
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
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
