"""Persistent research memory.

Vector search is a PHASE 2 deliverable. The column exists so migrations are
stable, but nothing in PHASE 1 writes or ranks embeddings.
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

    embedding: Mapped[list[float] | None] = mapped_column(Embedding())
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
