"""Memory access.

Search ranks by vector cosine (pgvector on PostgreSQL, a bounded Python scan
elsewhere). The response always states the method, whether a vector was used
and whether the embedder is semantic — today it is not: the only embedder
available without an external provider is lexical.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.deps import PageDep, SessionDep, SettingsDep, build_page, count_query
from app.models import Memory
from app.schemas.common import Page
from app.schemas.research import (
    MemoryClusterResponse,
    MemoryDigestResponse,
    MemoryHitOut,
    MemoryOut,
    MemorySearchResponse,
)
from app.services.memory import (
    MemoryHit,
    MemorySearchResult,
    get_memory_cluster,
    retrieve_related_memories,
    search_memory,
    summarize_memory,
)

router = APIRouter(prefix="/api/memory", tags=["memory"])


def _hits(hits: list[MemoryHit]) -> list[MemoryHitOut]:
    return [
        MemoryHitOut(score=round(hit.score, 6), memory=MemoryOut.model_validate(hit.memory))
        for hit in hits
    ]


def _search_response(result: MemorySearchResult, *, demo_default: bool) -> MemorySearchResponse:
    return MemorySearchResponse(
        query=result.query,
        method=result.method,
        vector=result.vector,
        semantic=result.semantic,
        embedding_model=result.embedding_model,
        items=_hits(result.hits),
        total_candidates=result.total_candidates,
        truncated=result.truncated,
        is_demo=(
            all(hit.memory.is_demo for hit in result.hits) if result.hits else demo_default
        ),
    )


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
async def search(
    session: SessionDep,
    settings: SettingsDep,
    q: str = Query(min_length=1, max_length=2000),
    memory_type: str | None = Query(default=None, alias="type"),
    mode: Literal["vector", "lexical"] = Query(default="vector"),
    limit: int = Query(default=20, ge=1, le=100),
    min_score: float | None = Query(default=None, ge=-1.0, le=1.0),
) -> MemorySearchResponse:
    result = await search_memory(
        session,
        q,
        limit=limit,
        memory_type=memory_type,
        min_score=min_score,
        mode=mode,
        settings=settings,
    )
    await session.commit()
    return _search_response(result, demo_default=settings.demo_mode)


@router.get("/summary", response_model=MemoryDigestResponse)
async def summary(
    session: SessionDep,
    settings: SettingsDep,
    memory_type: str | None = Query(default=None, alias="type"),
) -> MemoryDigestResponse:
    digest = await summarize_memory(session, memory_type=memory_type, settings=settings)
    return MemoryDigestResponse(
        method=digest.method,
        total=digest.total,
        with_vectors=digest.with_vectors,
        by_type=digest.by_type,
        recurring_terms=digest.recurring_terms,
        recent_failures=digest.recent_failures,
        sources=digest.sources,
        oldest_at=digest.oldest_at,
        newest_at=digest.newest_at,
        note=digest.note,
        is_demo=settings.demo_mode,
    )


@router.get("/{memory_id}", response_model=MemoryOut)
async def get_memory(session: SessionDep, memory_id: str) -> Memory:
    row = await session.get(Memory, memory_id)
    if row is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return row


@router.get("/{memory_id}/related", response_model=MemorySearchResponse)
async def related(
    session: SessionDep,
    settings: SettingsDep,
    memory_id: str,
    limit: int = Query(default=10, ge=1, le=50),
) -> MemorySearchResponse:
    try:
        result = await retrieve_related_memories(
            session, memory_id, limit=limit, settings=settings
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    await session.commit()
    return _search_response(result, demo_default=settings.demo_mode)


@router.get("/{memory_id}/cluster", response_model=MemoryClusterResponse)
async def cluster(
    session: SessionDep,
    settings: SettingsDep,
    memory_id: str,
    threshold: float | None = Query(default=None, ge=-1.0, le=1.0),
    limit: int = Query(default=25, ge=1, le=100),
) -> MemoryClusterResponse:
    try:
        hits = await get_memory_cluster(
            session, memory_id, threshold=threshold, limit=limit, settings=settings
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="memory not found") from exc
    await session.commit()
    return MemoryClusterResponse(
        seed_id=memory_id,
        threshold=(
            settings.memory_similarity_threshold if threshold is None else threshold
        ),
        method="cosine-threshold-v1",
        items=_hits(hits),
        is_demo=all(hit.memory.is_demo for hit in hits) if hits else settings.demo_mode,
    )
