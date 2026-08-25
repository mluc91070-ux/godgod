"""Fixture loading.

Fixtures are the ONLY data source in demo mode. Every row they produce is
flagged ``is_demo=True`` so demo data can never be mistaken for a real
observation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import get_settings

FIXTURE_FILES = (
    "tokens.json",
    "social.json",
    "research.json",
    "memories.json",
    "content.json",
    "events.json",
    "agents.json",
)


class FixtureError(RuntimeError):
    pass


def fixtures_dir() -> Path:
    configured = get_settings().fixtures_dir
    if configured:
        return Path(configured).resolve()
    # app/services/fixtures.py -> app -> backend -> <repo>
    return (Path(__file__).resolve().parents[3] / "data" / "fixtures").resolve()


def load_fixture(name: str) -> dict[str, Any]:
    path = fixtures_dir() / name
    if not path.is_file():
        raise FixtureError(f"missing fixture file: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise FixtureError(f"fixture {name} must contain a JSON object")
    return data


@lru_cache
def dataset_hash() -> str:
    """SHA-256 over the fixture files, in a fixed order.

    This is what ``dataset_hash`` on a demo experiment refers to: the exact
    bytes the demo dataset was built from.
    """
    digest = hashlib.sha256()
    for name in FIXTURE_FILES:
        path = fixtures_dir() / name
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
