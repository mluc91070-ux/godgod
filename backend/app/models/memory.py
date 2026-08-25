"""Persistent research memory.

Vectors are written by `app.services.memory.store_memory` and ranked either
by pgvector (PostgreSQL) or by a bounded Python cosine pass (SQLite).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.types import Embedding, JSONDict
from app.models.base import Entity


class Memory(Entity):
    __tablename__ = "memories"

    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSONDict)
    source: Mapped[str | None] = mapped_column(String(256))
    confidence: Mapped[float | None] = mapped_column(Float)

    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(36), index=True)

    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    """SHA-256 of the content. Storing the same memory twice is not learning."""

    embedding: Mapped[list[float] | None] = mapped_column(Embedding())
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    """Which embedder produced the vector. A vector with no named model
    cannot be reproduced or compared, so it is not trusted for ranking."""
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def has_vector(self) -> bool:
        """The API reports this instead of shipping 1536 floats to a browser."""
        return bool(self.embedding)
