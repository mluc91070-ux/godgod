"""The X provider (PHASE 7).

Read access to recent posts, plus a `create_post` that refuses.

Three constraints shape this file, and none of them are stylistic:

1. **Everything that comes back is untrusted.** A post body is data collected
   from a stranger. It is stored verbatim for research and wrapped by
   `wrap_untrusted` before it can reach a model — never treated as instruction,
   whatever it says.
2. **Publishing is not a capability of V1.** `create_post` exists so the
   interface is honest about what the platform offers, and it raises unless the
   configuration explicitly allows it, which in V1 it never does.
3. **Rate limits are reported, not absorbed.** A search that returned nothing
   because the quota is exhausted must not look like a search that found
   nothing. That distinction is the whole reason `XSearchResult` carries
   `rate_limited` rather than just a list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.untrusted import sanitize_external_text
from app.providers.base import ProviderNotConfigured, XProvider

API_ROOT = "https://api.x.com/2"

SEARCH_FIELDS = {
    "tweet.fields": "created_at,lang,public_metrics,author_id,referenced_tweets",
    "user.fields": "username,name,public_metrics,created_at",
    "expansions": "author_id",
}

MAX_RESULTS_CAP = 100
"""X rejects `max_results` above this on the recent-search endpoint."""


class XRateLimited(RuntimeError):
    """The quota is exhausted. Distinct from "there was nothing to find"."""

    def __init__(self, reset_at: datetime | None = None) -> None:
        self.reset_at = reset_at
        when = f" until {reset_at.isoformat()}" if reset_at else ""
        super().__init__(f"X rate limit reached{when}")


class XCallFailed(RuntimeError):
    """The API answered with an error, or did not answer."""


class PublishingDisabled(RuntimeError):
    """V1 does not publish. Raised instead of posting."""


@dataclass
class XPost:
    """One post, normalised. Fields X did not return stay None."""

    external_id: str
    text: str
    author_id: str | None
    author_handle: str | None
    posted_at: datetime | None
    lang: str | None
    likes: int | None
    reposts: int | None
    replies: int | None
    is_repost: bool

    def as_row(self, *, matched_terms: list[str] | None = None) -> dict[str, Any]:
        """The shape the ingestion path stores. Text is stored verbatim."""
        return {
            "platform": "x",
            "external_id": self.external_id,
            "text": self.text,
            "posted_at": self.posted_at,
            "lang": self.lang,
            "likes": self.likes,
            "reposts": self.reposts,
            "replies": self.replies,
            "handle": self.author_handle,
            "author_id": self.author_id,
            "matched_terms": matched_terms or [],
            "source": "x-recent-search",
        }


@dataclass
class XSearchResult:
    posts: list[XPost] = field(default_factory=list)
    rate_limited: bool = False
    """True when the quota stopped the search. Not the same as no results."""
    reset_at: datetime | None = None
    next_token: str | None = None
    requested: str = ""

    @property
    def usable(self) -> bool:
        return not self.rate_limited


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _normalise(payload: dict[str, Any]) -> list[XPost]:
    """Map the API response onto XPost, leaving absent fields absent."""
    users = {
        user["id"]: user
        for user in ((payload.get("includes") or {}).get("users") or [])
        if user.get("id")
    }
    posts: list[XPost] = []
    for item in payload.get("data") or []:
        metrics = item.get("public_metrics") or {}
        author_id = item.get("author_id")
        author = users.get(author_id) or {}
        referenced = item.get("referenced_tweets") or []
        posts.append(
            XPost(
                external_id=str(item.get("id")),
                # Sanitised on the way in: control characters and forged fence
                # markers are stripped before the text is ever stored.
                text=sanitize_external_text(item.get("text") or ""),
                author_id=author_id,
                author_handle=author.get("username"),
                posted_at=_parse_dt(item.get("created_at")),
                lang=item.get("lang"),
                likes=metrics.get("like_count"),
                reposts=metrics.get("retweet_count"),
                replies=metrics.get("reply_count"),
                is_repost=any(ref.get("type") == "retweeted" for ref in referenced),
            )
        )
    return posts


class NullXProvider(XProvider):
    """What runs with no bearer token. It refuses; it never returns [] quietly."""

    name = "x-none"
    implemented = False

    async def search_recent_posts(self, query: str, limit: int = 50, since_id: str | None = None):
        raise ProviderNotConfigured(
            "X_BEARER_TOKEN is not set. Reading posts needs a bearer token with "
            "access to the recent-search endpoint; no social data is collected "
            "until one is configured."
        )

    async def get_user(self, handle: str):
        raise ProviderNotConfigured("X_BEARER_TOKEN is not set")

    async def get_user_posts(self, handle: str, limit: int = 50):
        raise ProviderNotConfigured("X_BEARER_TOKEN is not set")

    async def get_mentions(self, limit: int = 50):
        raise ProviderNotConfigured("X_BEARER_TOKEN is not set")

    async def create_post(self, text: str, reply_to: str | None = None):
        raise PublishingDisabled("V1 does not publish. X_MODE is draft.")


class HttpXProvider(XProvider):
    """Recent search over the v2 API.

    Read-only in practice: `create_post` is present because the interface
    declares it, and it refuses.
    """

    name = "x"
    implemented = True

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.x_bearer_token:
            raise ProviderNotConfigured("X_BEARER_TOKEN is not set")
        self._settings = settings
        self._token = settings.x_bearer_token
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "godgod-research/0.1 (read-only)",
        }

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async def call(client: httpx.AsyncClient) -> httpx.Response:
            return await client.get(f"{API_ROOT}{path}", params=params, headers=self._headers())

        try:
            if self._client is not None:
                response = await call(self._client)
            else:
                async with httpx.AsyncClient(timeout=self._settings.x_timeout_seconds) as client:
                    response = await call(client)
        except httpx.HTTPError as exc:
            raise XCallFailed(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code == 429:
            reset = response.headers.get("x-rate-limit-reset")
            reset_at = (
                datetime.fromtimestamp(int(reset), tz=UTC)
                if reset and reset.isdigit()
                else None
            )
            raise XRateLimited(reset_at)

        if response.status_code == 401:
            raise ProviderNotConfigured(
                "X rejected the bearer token (401). Check X_BEARER_TOKEN."
            )
        if response.status_code == 403:
            raise XCallFailed(
                "X refused the request (403). The recent-search endpoint is not "
                "included in every access tier; check what the project is entitled to."
            )
        if response.status_code != 200:
            raise XCallFailed(f"HTTP {response.status_code}: {response.text[:300]}")

        return response.json()

    async def search_recent_posts(
        self, query: str, limit: int = 50, since_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Interface method. `search` below returns the richer result."""
        result = await self.search(query, limit=limit, since_id=since_id)
        return [post.as_row() for post in result.posts]

    async def search(
        self,
        query: str,
        *,
        limit: int = 50,
        since_id: str | None = None,
        next_token: str | None = None,
    ) -> XSearchResult:
        """One page of recent posts, or an explicit rate-limited result."""
        params: dict[str, Any] = {
            "query": query,
            "max_results": max(10, min(limit, MAX_RESULTS_CAP)),
            **SEARCH_FIELDS,
        }
        if since_id:
            params["since_id"] = since_id
        if next_token:
            params["next_token"] = next_token

        try:
            payload = await self._get("/tweets/search/recent", params)
        except XRateLimited as exc:
            return XSearchResult(rate_limited=True, reset_at=exc.reset_at, requested=query)

        meta = payload.get("meta") or {}
        return XSearchResult(
            posts=_normalise(payload),
            next_token=meta.get("next_token"),
            requested=query,
        )

    async def get_user(self, handle: str) -> dict[str, Any] | None:
        payload = await self._get(
            f"/users/by/username/{handle.lstrip('@')}",
            {"user.fields": SEARCH_FIELDS["user.fields"]},
        )
        return payload.get("data")

    async def get_user_posts(self, handle: str, limit: int = 50) -> list[dict[str, Any]]:
        user = await self.get_user(handle)
        if not user:
            return []
        payload = await self._get(
            f"/users/{user['id']}/tweets",
            {"max_results": max(5, min(limit, MAX_RESULTS_CAP)), **SEARCH_FIELDS},
        )
        return [post.as_row() for post in _normalise(payload)]

    async def get_mentions(self, limit: int = 50) -> list[dict[str, Any]]:
        raise ProviderNotConfigured(
            "Reading mentions needs the authenticated user's id, which requires "
            "user-context OAuth rather than an app bearer token. Not implemented."
        )

    async def create_post(self, text: str, reply_to: str | None = None) -> dict[str, Any]:
        """Never posts in V1.

        The check is on configuration, not on a caller's intention: there is no
        argument that makes this publish while X_MODE is draft.
        """
        raise PublishingDisabled(
            f"X_MODE={self._settings.x_mode} and autonomy level "
            f"{self._settings.autonomy_level}. V1 drafts; a human publishes."
        )


_cache: dict[tuple, XProvider] = {}


def get_x_provider(settings: Settings | None = None) -> XProvider:
    settings = settings or get_settings()
    key = (settings.x_bearer_token, settings.x_timeout_seconds)
    provider = _cache.get(key)
    if provider is None:
        provider = HttpXProvider(settings) if settings.x_bearer_token else NullXProvider()
        _cache[key] = provider
    return provider


def reset_x_provider() -> None:
    _cache.clear()
