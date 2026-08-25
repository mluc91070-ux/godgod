"""store_memory / search_memory / retrieve_related / cluster / digest."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Memory
from app.services.memory import (
    get_memory_cluster,
    retrieve_related_memories,
    search_memory,
    store_memory,
    summarize_memory,
)


async def test_store_embeds_and_records_the_model(session, seeded):
    result = await store_memory(
        session,
        memory_type="RESULT",
        content="liquidity withdrawal followed sustained concentration in 3 of 4 cases",
        summary="concentration preceded withdrawal",
        source="test",
        confidence=0.4,
    )
    assert result.created is True
    assert result.memory.embedding is not None
    assert len(result.memory.embedding) == 1536
    assert result.memory.embedding_model == "local-hashing-v1"
    assert result.memory.content_hash


async def test_storing_the_same_content_twice_is_not_learning(session, seeded):
    first = await store_memory(session, memory_type="RESULT", content="the same sentence")
    second = await store_memory(session, memory_type="RESULT", content="the same sentence")

    assert second.created is False
    assert second.memory.id == first.memory.id
    assert second.memory.access_count == 1

    rows = (
        await session.scalars(select(Memory).where(Memory.content == "the same sentence"))
    ).all()
    assert len(rows) == 1


async def test_same_text_under_a_different_type_is_a_different_memory(session, seeded):
    await store_memory(session, memory_type="RESULT", content="ambiguous line")
    other = await store_memory(session, memory_type="NARRATIVE", content="ambiguous line")
    assert other.created is True


async def test_seeded_memories_all_carry_reproducible_vectors(session, seeded):
    rows = (await session.scalars(select(Memory))).all()
    assert rows
    for row in rows:
        assert row.embedding is not None
        assert row.embedding_model == "local-hashing-v1", "a vector with no named model is unusable"
        assert row.content_hash


async def test_search_ranks_the_relevant_memory_first(session, seeded):
    result = await search_memory(session, "market regime split changed the sign")

    assert result.vector is True
    assert result.semantic is False, "the local embedder is lexical, and must say so"
    assert result.method == "vector-cosine/python-scan"
    assert result.hits
    assert "regime" in result.hits[0].memory.content.lower()
    assert result.hits[0].score > result.hits[-1].score or len(result.hits) == 1


async def test_search_scores_are_bounded_cosines(session, seeded):
    result = await search_memory(session, "attention propagation")
    for hit in result.hits:
        assert -1.0 <= hit.score <= 1.0


async def test_search_returns_nothing_rather_than_a_weak_guess(session, seeded):
    result = await search_memory(session, "quantum chromodynamics lattice gauge")
    assert result.hits == []
    assert result.total_candidates > 0, "candidates existed; none cleared the threshold"


async def test_search_can_filter_by_type(session, seeded):
    result = await search_memory(session, "rejected hypothesis", memory_type="failure")
    assert result.hits
    assert {hit.memory.memory_type for hit in result.hits} == {"FAILURE"}


async def test_lexical_mode_is_still_available(session, seeded):
    result = await search_memory(session, "regime", mode="lexical")
    assert result.vector is False
    assert result.method == "lexical-substring-v1"
    assert result.hits


async def test_search_records_that_a_memory_was_consulted(session, seeded):
    before = (
        await session.scalars(select(Memory).where(Memory.memory_type == "FAILURE"))
    ).all()[0]
    assert before.access_count == 0

    await search_memory(session, "rejected when the sample was split by market regime")
    await session.commit()

    after = await session.get(Memory, before.id)
    assert after.access_count >= 1
    assert after.last_accessed_at is not None


async def test_related_excludes_the_seed(session, seeded):
    seed = (
        await session.scalars(select(Memory).where(Memory.memory_type == "FAILURE"))
    ).all()[0]

    result = await retrieve_related_memories(session, seed, limit=5)
    assert seed.id not in {hit.memory.id for hit in result.hits}


async def test_related_raises_for_an_unknown_memory(session, seeded):
    with pytest.raises(LookupError):
        await retrieve_related_memories(session, "no-such-memory")


async def test_cluster_starts_with_the_seed_at_similarity_one(session, seeded):
    seed = (await session.scalars(select(Memory))).all()[0]
    cluster = await get_memory_cluster(session, seed, threshold=0.1)

    assert cluster[0].memory.id == seed.id
    assert cluster[0].score == 1.0
    assert all(hit.score >= 0.1 for hit in cluster[1:])


async def test_a_high_threshold_leaves_the_seed_alone(session, seeded):
    seed = (await session.scalars(select(Memory))).all()[0]
    cluster = await get_memory_cluster(session, seed, threshold=0.99)
    assert len(cluster) == 1


async def test_threshold_separates_real_matches_from_hash_noise(session, seeded, settings):
    """The default threshold is a measured property of the embedder.

    If a change to the embedder collapses this gap, the constant in
    `Settings.memory_similarity_threshold` has to be re-measured, not nudged.
    """
    relevant = await search_memory(session, "rejected hypothesis", min_score=-1.0)
    noise = await search_memory(session, "quantum chromodynamics lattice gauge", min_score=-1.0)

    best_relevant = max(hit.score for hit in relevant.hits)
    worst_case_noise = max(hit.score for hit in noise.hits)

    assert worst_case_noise < settings.memory_similarity_threshold < best_relevant


async def test_digest_counts_what_is_stored(session, seeded):
    digest = await summarize_memory(session)

    assert digest.method == "deterministic-digest-v1"
    assert digest.total == 6
    assert digest.with_vectors == 6
    assert digest.by_type["FAILURE"] == 1
    assert digest.recent_failures
    assert digest.oldest_at is not None and digest.newest_at is not None
    assert "not interpret" in digest.note


async def test_digest_surfaces_recurring_terms(session, seeded):
    digest = await summarize_memory(session)
    terms = dict(digest.recurring_terms)
    assert terms, "six memories share vocabulary; the digest should show it"
    assert all(count > 1 for count in terms.values())


async def test_digest_of_an_empty_type_is_empty_not_invented(session, seeded):
    digest = await summarize_memory(session, memory_type="WALLET")
    assert digest.total == 0
    assert digest.by_type == {}
    assert digest.recurring_terms == []
