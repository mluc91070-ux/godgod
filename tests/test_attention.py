"""Measuring what people look up, without inventing anyone's indifference.

The social collector is gone and this replaced it. A ranking is a better
measurement than a feed of posts — a position at a time, countable, no model
near it — but it has three ways of quietly becoming a lie, and they are what
this file checks:

- a coin absent from the list must produce no row, because "not ranked" and
  "ranked last" are different facts and only one of them is true;
- a token is linked on a contract address and never on a symbol;
- a run that stopped resolving names must say so rather than returning a
  shorter list.

No network is touched here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AttentionSnapshot, Token
from app.providers.attention import (
    AttentionCallFailed,
    HttpAttentionProvider,
    NullAttentionProvider,
    TrendingCoin,
)
from app.providers.base import ProviderNotConfigured
from app.services.attention import ATTENTION_SOURCE, collect_attention

PONS = "0x39dbed3a2bd333467115de45665cc57f813c4571"
CASHCAT = "0x020bfc650a365f8bb26819deaabf3e21291018b4"
CHAIN = "robinhood"
AT = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


class FakeAttention:
    def __init__(
        self,
        *coins: TrendingCoin,
        platforms: dict[str, dict[str, str]] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._coins = list(coins)
        self._platforms = platforms or {}
        self._raises = raises
        self.resolved: list[str] = []

    async def trending(self):
        if self._raises:
            raise self._raises
        return self._coins

    async def platforms(self, ref: str):
        self.resolved.append(ref)
        return self._platforms.get(ref, {})


def coin(ref: str, rank: int, symbol: str = "TOK") -> TrendingCoin:
    return TrendingCoin(ref=ref, symbol=symbol, name=symbol, rank=rank, market_cap_rank=100)


@pytest_asyncio.fixture
async def attention_settings(settings):
    settings.demo_mode = False
    settings.attention_api_url = "https://attention.example/api/v3"
    settings.market_chains = ["solana", CHAIN]
    settings.attention_max_resolutions = 6
    return settings


# -- the provider -----------------------------------------------------------


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_the_ranking_is_read_as_positions(attention_settings) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "coins": [
                    {"item": {"id": "uniswap", "symbol": "UNI", "name": "Uniswap"}},
                    {"item": {"id": "pons", "symbol": "PONS", "name": "Pons"}},
                ]
            },
        )

    provider = HttpAttentionProvider(attention_settings, client=transport(handle))
    found = await provider.trending()

    # Position in the list, not the source's own score: a score can change
    # meaning between releases, an index cannot.
    assert [(item.ref, item.rank) for item in found] == [("uniswap", 0), ("pons", 1)]


async def test_a_rate_limited_source_is_named(attention_settings) -> None:
    provider = HttpAttentionProvider(
        attention_settings,
        client=transport(lambda request: httpx.Response(429, text="slow down")),
    )
    with pytest.raises(AttentionCallFailed, match="rate-limited"):
        await provider.trending()


async def test_platforms_come_back_lowercased(attention_settings) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"platforms": {"Robinhood": "0x39DBED" + "0" * 34}}
        )

    provider = HttpAttentionProvider(attention_settings, client=transport(handle))
    platforms = await provider.platforms("pons")

    assert platforms == {"robinhood": "0x39dbed" + "0" * 34}


async def test_an_unconfigured_source_refuses() -> None:
    with pytest.raises(ProviderNotConfigured, match="ATTENTION_API_URL"):
        await NullAttentionProvider().trending()


# -- the collector ----------------------------------------------------------


async def test_a_ranked_coin_is_linked_by_address(session, attention_settings) -> None:
    token = Token(address=PONS, chain=CHAIN, symbol="PONS", is_demo=False)
    session.add(token)
    await session.flush()

    provider = FakeAttention(coin("pons", 1, "PONS"), platforms={"pons": {CHAIN: PONS}})
    report = await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    assert report.stored == 1 and report.linked == 1
    row = await session.scalar(select(AttentionSnapshot))
    assert row.token_id == token.id
    assert row.rank == 1
    assert row.source == ATTENTION_SOURCE


async def test_a_matching_symbol_is_never_a_link(session, attention_settings) -> None:
    """The rule the social collector had, kept after it went.

    Two chains hold a dozen of most symbols. Linking on one would put someone
    else's attention on a real token's record.
    """
    token = Token(address=CASHCAT, chain=CHAIN, symbol="PONS", is_demo=False)
    session.add(token)
    await session.flush()

    provider = FakeAttention(coin("pons", 0, "PONS"), platforms={"pons": {}})
    report = await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    assert report.linked == 0
    row = await session.scalar(select(AttentionSnapshot))
    assert row.token_id is None
    assert row.symbol == "PONS", "the symbol is recorded, it is just not a join"
    assert report.dropped["no_address_reported"] == 1


async def test_a_coin_on_another_chain_is_named_apart(session, attention_settings) -> None:
    provider = FakeAttention(
        coin("some-coin", 0), platforms={"some-coin": {"ethereum": "0x" + "b" * 40}}
    )
    report = await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    # "lives somewhere we do not measure" is a real answer, and a different one
    # from "the feed did not say where it lives".
    assert report.dropped["not_on_a_measured_chain"] == 1
    assert report.dropped.get("no_address_reported") is None


async def test_an_unranked_token_gets_no_row(session, attention_settings) -> None:
    """The assertion this table exists for.

    A row for every token with rank 0 would be this system inventing everyone's
    indifference, and a detector reading it could not tell the difference.
    """
    session.add(Token(address=CASHCAT, chain=CHAIN, symbol="CASHCAT", is_demo=False))
    await session.flush()

    provider = FakeAttention(coin("pons", 0, "PONS"), platforms={"pons": {CHAIN: PONS}})
    await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    rows = (await session.scalars(select(AttentionSnapshot))).all()
    assert [row.ref for row in rows] == ["pons"]


async def test_the_resolution_budget_is_counted(session, attention_settings) -> None:
    attention_settings.attention_max_resolutions = 1
    provider = FakeAttention(
        coin("a", 0), coin("b", 1), coin("c", 2), platforms={"a": {CHAIN: PONS}}
    )
    report = await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    assert report.resolved == 1
    assert report.unresolved == 2
    assert report.dropped["address_not_resolved_this_run"] == 2
    # The rows are still stored: the ranking is what was measured, and the
    # address is a later join, not a condition of the reading.
    assert report.stored == 3


async def test_an_address_is_looked_up_once(session, attention_settings) -> None:
    """The mapping does not change, and the keyless tier is rate-limited."""
    provider = FakeAttention(coin("pons", 0), platforms={"pons": {CHAIN: PONS}})
    await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )
    later = AT.replace(hour=13)
    await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=later, commit=False
    )

    assert provider.resolved == ["pons"], "the second run read the row, not the network"
    rows = (await session.scalars(select(AttentionSnapshot))).all()
    assert len(rows) == 2 and all(row.address == PONS for row in rows)


async def test_one_reading_per_slot(session, attention_settings) -> None:
    provider = FakeAttention(coin("pons", 0), platforms={"pons": {CHAIN: PONS}})
    await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )
    again = await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    assert again.stored == 0
    assert again.dropped["already_sampled_this_slot"] == 1


async def test_a_dead_source_is_an_error_not_an_empty_ranking(
    session, attention_settings
) -> None:
    provider = FakeAttention(raises=AttentionCallFailed("the source is down"))
    report = await collect_attention(
        session, settings=attention_settings, provider=provider, as_of=AT, commit=False
    )

    assert report.error is not None
    assert report.as_dict()["complete"] is False
    assert report.stored == 0
    rows = (await session.scalars(select(AttentionSnapshot))).all()
    assert rows == []
