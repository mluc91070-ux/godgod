"""Social entities and the X content pipeline.

Every stored post body is untrusted input. It is persisted verbatim for
research, and always wrapped as data before it reaches a model.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.types import JSONDict
from app.models.base import Entity


class SocialAccount(Entity):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_social_account"),)

    platform: Mapped[str] = mapped_column(String(32), default="x", nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    handle: Mapped[str | None] = mapped_column(String(128), index=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    followers: Mapped[int | None] = mapped_column(Integer)
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_metadata: Mapped[dict | None] = mapped_column(JSONDict)

    posts: Mapped[list[SocialPost]] = relationship(back_populates="account")


class SocialPost(Entity):
    __tablename__ = "social_posts"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_social_post"),)

    platform: Mapped[str] = mapped_column(String(32), default="x", nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), index=True
    )
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str | None] = mapped_column(String(16))
    likes: Mapped[int | None] = mapped_column(Integer)
    reposts: Mapped[int | None] = mapped_column(Integer)
    replies: Mapped[int | None] = mapped_column(Integer)
    matched_terms: Mapped[list | None] = mapped_column(JSONDict)
    mentions_token_address: Mapped[str | None] = mapped_column(String(64), index=True)
    source: Mapped[str | None] = mapped_column(String(128))

    account: Mapped[SocialAccount | None] = relationship(back_populates="posts")


class ContentDraft(Entity):
    """A candidate public message. Nothing leaves the system without approval."""

    __tablename__ = "content_drafts"

    content_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """OBSERVATION | HYPOTHESIS | EXPERIMENT | RESULT | FAILURE | DISCOVERY | THOUGHT"""
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)
    """PENDING | APPROVED | REJECTED | PUBLISHED"""
    reviewer_verdict: Mapped[str | None] = mapped_column(String(32))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    source_kind: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    """Row this draft is derived from. A draft with no source cannot be approved."""

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(128))

    published: Mapped[PublishedPost | None] = relationship(back_populates="draft", uselist=False)


class PublishedPost(Entity):
    __tablename__ = "published_posts"

    draft_id: Mapped[str] = mapped_column(
        ForeignKey("content_drafts.id", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(32), default="x", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(512))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    engagement: Mapped[dict | None] = mapped_column(JSONDict)
    engagement_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reach_score: Mapped[float | None] = mapped_column(Float)

    draft: Mapped[ContentDraft] = relationship(back_populates="published")
