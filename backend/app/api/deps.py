"""Shared API dependencies."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.common import Page

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PageDep = Annotated[Pagination, Depends(pagination)]


async def count_query(session: AsyncSession, stmt: Any) -> int:
    subquery = stmt.order_by(None).subquery()
    return int(await session.scalar(select(func.count()).select_from(subquery)) or 0)


def build_page(
    items: Sequence[Any], schema: type, total: int, page: Pagination, settings: Settings
) -> Page:
    parsed = [schema.model_validate(item) for item in items]
    all_demo = (
        all(getattr(item, "is_demo", False) for item in items) if items else settings.demo_mode
    )
    return Page(items=parsed, total=total, limit=page.limit, offset=page.offset, is_demo=all_demo)


async def require_admin(
    settings: SettingsDep,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> str:
    """Guard for every state-changing endpoint.

    When ADMIN_TOKEN is unset the guard refuses rather than allowing: an
    unconfigured deployment is a locked deployment, not an open one.
    """
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN is not configured; approval endpoints are disabled.",
        )
    if x_admin_token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token"
        )
    return "admin"


AdminDep = Annotated[str, Depends(require_admin)]
