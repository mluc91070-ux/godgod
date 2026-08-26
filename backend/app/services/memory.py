"""Research memory.

Five operations, matching the architecture: `store_memory`, `search_memory`,
`retrieve_related_memories`, `get_memory_cluster`, `summarize_memory`.

Ranking runs one of two ways:

- **PostgreSQL** — pgvector orders by `<=>` (cosine distance) in the database.
- **anything else** — a bounded Python cosine pass over at most
  ``MEMORY_SCAN_LIMIT`` rows.

Both report which path they took in `MemorySearchResult.method`, and neither
claims to be semantic: the only embedder available today is lexical (see
`app/services/embeddings.py`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Float, Select, func, or_, select, text, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import Memory
from app.models.base import utcnow
from app.services.embeddings import (
    EmbeddingProvider,
    content_hash,
    cosine,
    get_embedding_provider,
    tokenize,
)

LEXICAL_METHOD = "lexical-substring-v1"
VECTOR_PG_METHOD = "vector-cosine/pgvector"
VECTOR_PY_METHOD = "vector-cosine/python-scan"
DIGEST_METHOD = "deterministic-digest-v1"


@dataclass(frozen=True)
class MemoryHit:
    memory: Memory
    score: float
    """Cosine similarity in [-1, 1] for vector search, 1.0 for a lexical match."""


@dataclass(frozen=True)
class MemorySearchResult:
    query: str
    method: str
    vector: bool
    semantic: bool
    embedding_model: str | None
    hits: list[MemoryHit]
    total_candidates: int
    truncated: bool
    """True when the scan hit MEMORY_SCAN_LIMIT and could not see every row."""


@dataclass(frozen=True)
class StoreResult:
    memory: Memory
    created: bool


@dataclass
class MemoryDigest:
    method: str = DIGEST_METHOD
    total: int = 0
    with_vectors: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    recurring_terms: list[tuple[str, int]] = field(default_factory=list)
    recent_failures: list[str] = field(default_factory=list)
    sources: dict[str, int] = field(default_factory=dict)
    oldest_at: datetime | None = None
    newest_at: datetime | None = None
    note: str = (
        "Structural digest computed from stored rows. It counts and quotes; it does "
        "not interpret. A written synthesis requires a model provider."
    )


def dialect_name(session: AsyncSession) -> str:
    try:
        return session.get_bind().dialect.name
    except Exception:  # pragma: no cover - defensive, unbound session
        return "unknown"


def _apply_filters(
    stmt: Select,
    *,
    memory_type: str | None,
    min_confidence: float | None,
    include_demo: bool,
) -> Select:
    if memory_type:
        stmt = stmt.where(Memory.memory_type == memory_type.upper())
    if min_confidence is not None:
        stmt = stmt.where(Memory.confidence >= min_confidence)
    if not include_demo:
        stmt = stmt.where(Memory.is_demo.is_(False))
    return stmt


async def store_memory(
    session: AsyncSession,
    *,
    memory_type: str,
    content: str,
    summary: str | None = None,
    meta: dict[str, Any] | None = None,
    source: str | None = None,
    confidence: float | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    is_demo: bool = False,
    provider: EmbeddingProvider | None = None,
    commit: bool = True,
) -> StoreResult:
    """Write one memory, embedding it and refusing to duplicate it.

    Duplicate detection is on the exact content hash: storing the same
    sentence twice is not learning, and it would skew every later count.
    """
    provider = provider or get_embedding_provider()
    digest = content_hash(content)

    existing = await session.scalar(
        select(Memory).where(
            Memory.content_hash == digest,
            Memory.memory_type == memory_type.upper(),
        )
    )
    if existing is not None:
        existing.access_count += 1
        existing.last_accessed_at = utcnow()
        if confidence is not None:
            existing.confidence = confidence
        if commit:
            await session.commit()
        return StoreResult(memory=existing, created=False)

    try:
        embedding = provider.embed(content if not summary else f"{summary}\n{content}")
        embedding_model = provider.name
    except RuntimeError:
        # EMBEDDING_PROVIDER=none. Store the text; leave the vector empty
        # rather than writing a placeholder nobody could reproduce.
        embedding = None
        embedding_model = None

    memory = Memory(
        memory_type=memory_type.upper(),
        content=content,
        summary=summary,
        meta=meta,
        source=source,
        confidence=confidence,
        ref_type=ref_type,
        ref_id=ref_id,
        content_hash=digest,
        embedding=embedding,
        embedding_model=embedding_model,
        is_demo=is_demo,
    )
    session.add(memory)
    await session.flush()
    if commit:
        await session.commit()
    return StoreResult(memory=memory, created=True)


def cosine_distance_expression(query_vector: list[float]):
    """The pgvector `<=>` distance, as an expression that can be labelled.

    A bare `text()` clause carries no type, so it cannot be used as a SELECT
    column or labelled — which is exactly how the ranking path broke on its
    first real deploy, long after the build looked fine. `type_coerce` gives it
    a type without changing the SQL, and the vector stays a bound parameter
    rather than being interpolated into the statement.
    """
    literal = "[" + ",".join(f"{value:.7f}" for value in query_vector) + "]"
    return type_coerce(
        text("memories.embedding <=> CAST(:qvec AS vector)").bindparams(qvec=literal),
        Float(),
    )


async def _rank_postgres(
    session: AsyncSession,
    query_vector: list[float],
    *,
    limit: int,
    memory_type: str | None,
    min_confidence: float | None,
    include_demo: bool,
    embedding_model: str,
) -> tuple[list[MemoryHit], int]:
    """pgvector ordering.

    First executed by the first production deploy, which is where the original
    version broke. The Python path below stays the one covered by tests on a
    machine without PostgreSQL; both are reached through the same public
    function, so a Postgres deployment exercises this one on its first search.
    """
    distance = cosine_distance_expression(query_vector)

    stmt = select(Memory, distance.label("distance")).where(
        Memory.embedding.is_not(None),
        Memory.embedding_model == embedding_model,
    )
    stmt = _apply_filters(
        stmt,
        memory_type=memory_type,
        min_confidence=min_confidence,
        include_demo=include_demo,
    )
    total = int(
        await session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        or 0
    )
    rows = (await session.execute(stmt.order_by(distance).limit(limit))).all()
    hits = [MemoryHit(memory=row[0], score=1.0 - float(row[1])) for row in rows]
    return hits, total


async def _rank_python(
    session: AsyncSession,
    query_vector: list[float],
    *,
    limit: int,
    memory_type: str | None,
    min_confidence: float | None,
    include_demo: bool,
    embedding_model: str,
    scan_limit: int,
) -> tuple[list[MemoryHit], int, bool]:
    stmt = select(Memory).where(
        Memory.embedding.is_not(None),
        Memory.embedding_model == embedding_model,
    )
    stmt = _apply_filters(
        stmt,
        memory_type=memory_type,
        min_confidence=min_confidence,
        include_demo=include_demo,
    )
    total = int(
        await session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        or 0
    )
    rows = (
        await session.scalars(stmt.order_by(Memory.created_at.desc()).limit(scan_limit))
    ).all()

    scored = [
        MemoryHit(memory=row, score=cosine(query_vector, row.embedding or []))
        for row in rows
    ]
    scored.sort(key=lambda hit: hit.score, reverse=True)
    return scored[:limit], total, total > len(rows)


async def _lexical(
    session: AsyncSession,
    query: str,
    *,
    limit: int,
    memory_type: str | None,
    min_confidence: float | None,
    include_demo: bool,
) -> tuple[list[MemoryHit], int]:
    pattern = f"%{query.lower()}%"
    stmt = select(Memory).where(
        or_(Memory.content.ilike(pattern), Memory.summary.ilike(pattern))
    )
    stmt = _apply_filters(
        stmt,
        memory_type=memory_type,
        min_confidence=min_confidence,
        include_demo=include_demo,
    )
    total = int(
        await session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        or 0
    )
    rows = (
        await session.scalars(stmt.order_by(Memory.created_at.desc()).limit(limit))
    ).all()
    return [MemoryHit(memory=row, score=1.0) for row in rows], total


async def search_memory(
    session: AsyncSession,
    query: str,
    *,
    limit: int | None = None,
    memory_type: str | None = None,
    min_confidence: float | None = None,
    min_score: float | None = None,
    include_demo: bool = True,
    mode: str = "vector",
    settings: Settings | None = None,
) -> MemorySearchResult:
    """Rank memories against a query. `mode` is "vector" or "lexical"."""
    settings = settings or get_settings()
    provider = get_embedding_provider(settings)
    limit = limit or settings.memory_retrieval_limit

    use_vector = mode == "vector" and settings.embedding_provider != "none"
    if not use_vector:
        hits, total = await _lexical(
            session,
            query,
            limit=limit,
            memory_type=memory_type,
            min_confidence=min_confidence,
            include_demo=include_demo,
        )
        return MemorySearchResult(
            query=query,
            method=LEXICAL_METHOD,
            vector=False,
            semantic=False,
            embedding_model=None,
            hits=hits,
            total_candidates=total,
            truncated=False,
        )

    query_vector = provider.embed(query)
    is_postgres = dialect_name(session) == "postgresql"

    if is_postgres:
        hits, total = await _rank_postgres(
            session,
            query_vector,
            limit=limit,
            memory_type=memory_type,
            min_confidence=min_confidence,
            include_demo=include_demo,
            embedding_model=provider.name,
        )
        truncated = False
        method = VECTOR_PG_METHOD
    else:
        hits, total, truncated = await _rank_python(
            session,
            query_vector,
            limit=limit,
            memory_type=memory_type,
            min_confidence=min_confidence,
            include_demo=include_demo,
            embedding_model=provider.name,
            scan_limit=settings.memory_scan_limit,
        )
        method = VECTOR_PY_METHOD

    floor = settings.memory_similarity_threshold if min_score is None else min_score
    hits = [hit for hit in hits if hit.score >= floor]

    for hit in hits:
        hit.memory.access_count += 1
        hit.memory.last_accessed_at = utcnow()
    await session.flush()

    return MemorySearchResult(
        query=query,
        method=method,
        vector=True,
        semantic=provider.semantic,
        embedding_model=provider.name,
        hits=hits,
        total_candidates=total,
        truncated=truncated,
    )


async def retrieve_related_memories(
    session: AsyncSession,
    memory: Memory | str,
    *,
    limit: int | None = None,
    min_score: float | None = None,
    settings: Settings | None = None,
) -> MemorySearchResult:
    """Neighbours of one memory, excluding itself."""
    settings = settings or get_settings()
    if isinstance(memory, str):
        found = await session.get(Memory, memory)
        if found is None:
            raise LookupError(f"memory {memory} not found")
        memory = found

    seed_text = f"{memory.summary}\n{memory.content}" if memory.summary else memory.content
    result = await search_memory(
        session,
        seed_text,
        limit=(limit or settings.memory_retrieval_limit) + 1,
        min_score=min_score,
        settings=settings,
    )
    hits = [hit for hit in result.hits if hit.memory.id != memory.id]
    return MemorySearchResult(
        query=seed_text,
        method=result.method,
        vector=result.vector,
        semantic=result.semantic,
        embedding_model=result.embedding_model,
        hits=hits[: (limit or settings.memory_retrieval_limit)],
        total_candidates=result.total_candidates,
        truncated=result.truncated,
    )


async def get_memory_cluster(
    session: AsyncSession,
    seed: Memory | str,
    *,
    threshold: float | None = None,
    limit: int = 25,
    settings: Settings | None = None,
) -> list[MemoryHit]:
    """The seed plus every memory above `threshold` similarity to it.

    Single-pass and deterministic: no transitive expansion, so the cluster
    means exactly "close to this one", not "somehow connected".
    """
    settings = settings or get_settings()
    if isinstance(seed, str):
        found = await session.get(Memory, seed)
        if found is None:
            raise LookupError(f"memory {seed} not found")
        seed = found

    threshold = settings.memory_similarity_threshold if threshold is None else threshold
    related = await retrieve_related_memories(
        session, seed, limit=limit, min_score=threshold, settings=settings
    )
    return [MemoryHit(memory=seed, score=1.0), *related.hits]


async def summarize_memory(
    session: AsyncSession,
    *,
    memory_type: str | None = None,
    include_demo: bool = True,
    top_terms: int = 12,
    settings: Settings | None = None,
) -> MemoryDigest:
    """A structural digest of what is stored. Counts and quotes, no interpretation."""
    settings = settings or get_settings()
    stmt = _apply_filters(
        select(Memory),
        memory_type=memory_type,
        min_confidence=None,
        include_demo=include_demo,
    )
    rows = (await session.scalars(stmt.order_by(Memory.created_at.desc()))).all()

    digest = MemoryDigest(total=len(rows))
    if not rows:
        return digest

    digest.with_vectors = sum(1 for row in rows if row.embedding)
    digest.by_type = dict(Counter(row.memory_type for row in rows).most_common())
    digest.sources = dict(Counter(row.source or "unknown" for row in rows).most_common())

    document_frequency: Counter[str] = Counter()
    for row in rows:
        document_frequency.update(set(tokenize(f"{row.summary or ''} {row.content}")))
    digest.recurring_terms = [
        (term, count) for term, count in document_frequency.most_common(top_terms) if count > 1
    ]

    digest.recent_failures = [
        row.summary or row.content for row in rows if row.memory_type == "FAILURE"
    ][:5]

    timestamps = [row.created_at for row in rows]
    digest.oldest_at = min(timestamps)
    digest.newest_at = max(timestamps)
    return digest
