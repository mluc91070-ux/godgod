"""Configuration that has to survive contact with a real deployment.

These are the settings a container passes in as environment strings. A field
that only parses in a test harness is a field that takes the site down on the
first deploy.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def build(**env: str) -> Settings:
    """Construct settings from environment values, as a container would."""
    return Settings(_env_file=None, **env)


def test_cors_origins_reads_a_plain_comma_separated_string(monkeypatch) -> None:
    """The regression this test exists for: `CORS_ORIGINS=https://site` used to
    crash at startup because a list field was JSON-decoded before validation."""
    monkeypatch.setenv("CORS_ORIGINS", "https://godgod.example")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["https://godgod.example"]


def test_cors_origins_reads_several_origins(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    assert Settings(_env_file=None).cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_defaults_to_local_dev(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings(_env_file=None).cors_origins == ["http://localhost:3000"]


def test_wallet_execution_cannot_be_switched_on(monkeypatch) -> None:
    """There is no environment variable that turns it on, because there is no
    code path it could enable."""
    monkeypatch.setenv("WALLET_EXECUTION_ENABLED", "true")
    assert Settings(_env_file=None).wallet_execution_enabled is False


def test_autonomy_level_is_validated() -> None:
    with pytest.raises(ValueError):
        build(autonomy_level=9)


@pytest.mark.parametrize("url", ["postgresql+psycopg://u:p@h/db", "postgresql://u:p@h/db"])
def test_postgres_is_detected(url: str) -> None:
    assert build(database_url=url).is_postgres is True


def test_sqlite_is_not_postgres() -> None:
    assert build(database_url="sqlite+aiosqlite:///./x.db").is_postgres is False


def test_prices_default_to_unset_not_zero() -> None:
    """Unpriced must be distinguishable from free."""
    settings = build()
    assert settings.model_price_input_usd_per_mtok is None
    assert settings.model_price_output_usd_per_mtok is None


def test_no_model_name_is_baked_into_the_defaults() -> None:
    settings = build()
    for role in ("model_fast", "model_reasoning", "model_writer", "model_critic"):
        assert getattr(settings, role) is None, f"{role} must come from the environment"


def test_stream_limits_have_safe_defaults() -> None:
    settings = build()
    assert settings.stream_max_seconds > 0, "a connection that never ages out never reconnects"
    assert settings.stream_poll_seconds > 0
    assert settings.stream_replay_events > 0
