"""Portable column types.

The production target is PostgreSQL + pgvector. Tests and local demo runs
use SQLite, so vector and JSONB columns degrade to portable equivalents.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import JSON, Text
from sqlalchemy.types import TypeDecorator

EMBEDDING_DIM = 1536


class JSONDict(TypeDecorator):
    """JSONB on PostgreSQL, JSON everywhere else."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class Embedding(TypeDecorator):
    """pgvector ``vector`` on PostgreSQL, JSON-encoded list elsewhere.

    Vector similarity search is a PostgreSQL-only capability; the SQLite
    fallback stores the value but cannot index or rank by distance.
    """

    impl = Text
    cache_ok = True

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.dim = dim
        super().__init__()

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(list(value))

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None or dialect.name == "postgresql":
            return value
        return json.loads(value)
