"""The local embedder: deterministic, reproducible, and honest about being lexical."""

from __future__ import annotations

import math

import pytest

from app.services.embeddings import (
    LocalHashingEmbedding,
    NullEmbedding,
    content_hash,
    cosine,
    get_embedding_provider,
    tokenize,
)

TEXT_A = "social velocity rose while unique buyers stayed flat"
TEXT_B = "buyer participation stayed flat while social velocity increased"
TEXT_C = "holder concentration remained above the threshold for seven hours"


@pytest.fixture
def embedder() -> LocalHashingEmbedding:
    return LocalHashingEmbedding(dim=256, name="test-hashing")


def test_embedding_is_deterministic_across_instances(embedder):
    other = LocalHashingEmbedding(dim=256, name="test-hashing")
    assert embedder.embed(TEXT_A) == other.embed(TEXT_A)


def test_embedding_has_the_declared_dimension(embedder):
    vector = embedder.embed(TEXT_A)
    assert len(vector) == 256


def test_embedding_is_l2_normalized(embedder):
    norm = math.sqrt(sum(value * value for value in embedder.embed(TEXT_A)))
    assert norm == pytest.approx(1.0, abs=1e-9)


def test_empty_text_gives_a_zero_vector_not_a_crash(embedder):
    vector = embedder.embed("   ")
    assert set(vector) == {0.0}
    assert cosine(vector, embedder.embed(TEXT_A)) == 0.0


def test_similar_wording_ranks_above_unrelated_wording(embedder):
    near = cosine(embedder.embed(TEXT_A), embedder.embed(TEXT_B))
    far = cosine(embedder.embed(TEXT_A), embedder.embed(TEXT_C))
    assert near > far


def test_identical_text_is_self_similar(embedder):
    assert cosine(embedder.embed(TEXT_A), embedder.embed(TEXT_A)) == pytest.approx(1.0)


def test_local_embedder_never_claims_to_be_semantic(embedder):
    assert embedder.semantic is False


def test_tokenizer_drops_stopwords_and_single_characters():
    assert tokenize("the signal is a b c gone") == ["signal", "gone"]


def test_content_hash_is_stable_and_whitespace_insensitive():
    assert content_hash("  a memory  ") == content_hash("a memory")
    assert content_hash("a memory") != content_hash("another memory")
    assert len(content_hash("x")) == 64


def test_disabled_provider_refuses_instead_of_faking_a_vector():
    with pytest.raises(RuntimeError, match="disabled"):
        NullEmbedding().embed("anything")


def test_provider_selection_follows_configuration(settings):
    provider = get_embedding_provider(settings)
    assert provider.name == settings.embedding_model
    assert provider.dim == settings.embedding_dim
