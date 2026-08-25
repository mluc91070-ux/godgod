"""Memory access.

PHASE 1 exposes lexical search only. Vector retrieval (pgvector) is a
PHASE 2 deliverable — the response says so explicitly via ``semantic``
rather than implying a capability that does not exist yet.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.api.deps import PageDep, SessionDep, SettingsDep, build_page, count_query
from app.models import Memory
from app.schemas.common import Page
from app.schemas.research import MemoryOut, MemorySearchResponse

router = APIRouter(prefix="/api/memory", tags=["memory"])

SEARCH_METHOD = "lexical-substring-v1"


@router.get("", response_model=Page[MemoryOut])
async def list_memories(
    session: SessionDep,
    settings: SettingsDep,
    page: PageDep,
    memory_type: str | None = Query(default=None, alias="type"),
) -> Page:
    stmt = select(Memory).order_by(Memory.created_at.desc())
    if memory_type:
        stmt = stmt.where(Memory.memory_type == memory_type.upper())
    total = await count_query(session, stmt)
    rows = (await session.scalars(stmt.limit(page.limit).offset(page.offset))).all()
    return build_page(rows, MemoryOut, total, page, settings)


@router.get("/search", response_model=MemorySearchResponse)
async def search_memory(
    session: SessionDep,
    settings: SettingsDep,
    q: str = Query(min_length=1, max_length=512),
    memory_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=20, ge=1, le=100),
) -> MemorySearchResponse:
    pattern = f"%{q.lower()}%"
    stmt = select(Memory).where(
        or_(
            Memory.content.ilike(pattern),
            Memory.summary.ilike(pattern),
        )
    )
    if memory_type:
        stmt = stmt.where(Memory.memory_type == memory_type.upper())
    total = await count_query(session, stmt)
    rows = (
        await session.scalars(stmt.order_by(Memory.created_at.desc()).limit(limit))
    ).all()
    items = [MemoryOut.model_validate(row) for row in rows]
    return MemorySearchResponse(
        query=q,
        method=SEARCH_METHOD,
        semantic=False,
        items=items,
        total=total,
        is_demo=all(row.is_demo for row in rows) if rows else settings.demo_mode,
    )
