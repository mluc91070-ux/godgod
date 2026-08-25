"""Embeddings.

The interface exists so a learned model can be swapped in without touching
the memory service. Today the only implementation is a deterministic
hashing embedder that runs locally and costs nothing.

Be precise about what that means: hashed bag-of-terms cosine is **lexical
similarity expressed as a vector**. It matches wording, not meaning. It is
not a semantic model, and nothing in this codebase may describe it as one —
`EmbeddingProvider.semantic` is the flag that carries that distinction all
the way to the API response.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from itertools import pairwise

from app.core.config import Settings, get_settings

_TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    """
    a an and are as at be been by for from had has have i if in into is it its of on or
    that the their then there these this to was were what when which who will with
    """.split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords removed, single characters dropped."""
    return [
        token
        for token in _TOKEN.findall(text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def content_hash(text: str) -> str:
    """Stable identity for a piece of remembered content (dedupe key)."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


class EmbeddingProvider(ABC):
    name: str
    dim: int
    semantic: bool
    """False for lexical methods. Only a learned model may set this True."""

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class LocalHashingEmbedding(EmbeddingProvider):
    """Signed-hash bag of unigrams and bigrams, L2 normalized.

    Deterministic across processes and machines: it uses blake2b, never
    Python's randomized `hash()`. Same text in, same vector out, forever —
    which is what makes a stored vector reproducible.
    """

    semantic = False

    def __init__(self, dim: int = 1536, name: str = "local-hashing-v1") -> None:
        self.dim = dim
        self.name = name

    def _bucket(self, term: str) -> tuple[int, float]:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % self.dim
        sign = 1.0 if (value >> 63) & 1 else -1.0
        return index, sign

    def embed(self, text: str) -> list[float]:
        tokens = tokenize(text)
        terms = Counter(tokens)
        terms.update(f"{first}_{second}" for first, second in pairwise(tokens))

        vector = [0.0] * self.dim
        for term, count in terms.items():
            index, sign = self._bucket(term)
            vector[index] += sign * (1.0 + math.log(count))

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


class NullEmbedding(EmbeddingProvider):
    """Explicitly disabled. Memory still stores text; it just cannot rank."""

    name = "none"
    semantic = False

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        raise RuntimeError(
            "EMBEDDING_PROVIDER=none: vectors are disabled, use lexical search"
        )


_PROVIDERS: dict[tuple[str, str, int], EmbeddingProvider] = {}


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    """Cached by configuration, not by Settings identity.

    Settings instances are not hashable, so the cache key is the three values
    that actually determine the provider.
    """
    settings = settings or get_settings()
    key = (settings.embedding_provider, settings.embedding_model, settings.embedding_dim)
    if key not in _PROVIDERS:
        _PROVIDERS[key] = (
            NullEmbedding(dim=settings.embedding_dim)
            if settings.embedding_provider == "none"
            else LocalHashingEmbedding(dim=settings.embedding_dim, name=settings.embedding_model)
        )
    return _PROVIDERS[key]


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity. Inputs from `embed` are already normalized."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)
