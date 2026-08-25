"""Declarative base and shared mixins."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """All GODGOD tables inherit from this."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        nullable=False,
    )


class UUIDPrimaryKey:
    """Internal rows get UUID string ids.

    Blockchain identifiers are NEVER used as primary keys: they are stored
    as plain strings in dedicated columns.
    """

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class DemoFlagMixin:
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)


class Entity(UUIDPrimaryKey, TimestampMixin, DemoFlagMixin, Base):
    __abstract__ = True
