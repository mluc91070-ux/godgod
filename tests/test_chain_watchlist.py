"""Tokens named by hand: measured, shown, and kept out of every comparison.

A watchlist is the most biased frame there is. The other two are populations —
whatever the feed promoted, whatever curve filled — and this one is a list
somebody wrote after seeing which tokens did well. Every entry is a survivor by
construction.

So the two uses are separated instead of blurred. The rows are collected like
any other, and `build_dataset` drops them under a named reason. Most of this
file is about that second half, because it is the one that would be easy to
skip and impossible to notice.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select

from app.models import Token, TokenSnapshot
from app.providers.market import MarketSnapshot
from app.services.chain import PROMOTED, WATCHLIST, collect_chain
from app.services.research.dataset import build_dataset
from app.services.research.templates import TEMPLATES

NAMED = "0x39dBED3a2bd333467115dE45665cC57F813C4571"
MISSING = "0x0000000000000000000000000000000000000dead"
FOUND_BY_FEED = "0x020bfC650A365f8BB26819deAAbF3E21291018b4"
CHAIN = "robinhood"


def snapshot(address: str, chain: str = CHAIN, liquidity: float = 50_000.0) -> MarketSnapshot:
    return MarketSnapshot(
        address=address,
        chain=chain,
        symbol="TOK",
        name="A Token",
        market_cap_usd=9_000_000.0,
        liquidity_usd=liquidity,
        volume_usd=120_000.0,
        volume_24h_usd=960_000.0,
        transactions=50,
        buys=30,
        sells=20,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


class FakeMarket:
    def __init__(self, *snapshots: MarketSnapshot, discovers: list[str] | None = None) -> None:
        self._snapshots = list(snapshots)
        self._discovers = discovers if discovers is not None else []

    async def search(self, query, limit=20):
        return await self.discover(limit)

    async def discover(self, limit=30):
        return [s for s in self._snapshots if s.address in self._discovers]

    async def get_snapshot(self, address, chain="solana"):
        return next((s for s in self._snapshots if s.address == address), None)

    async def snapshots(self, addresses, chain="solana"):
        wanted = {a.lower() for a in addresses}
        return [
            s for s in self._snapshots if s.address.lower() in wanted and s.chain == chain
        ]


class FakeChain:
    async def get_holder_distribution(self, mint):
        from app.providers.solana import HolderDistribution

        return HolderDistribution(top10_share=0.42, accounts_seen=20, supply=1_000.0)


@pytest_asyncio.fixture
async def watch_settings(settings):
    settings.demo_mode = False
    settings.solana_rpc_url = "https://rpc.example/godgod"
    settings.market_api_url = "https://market.example"
    settings.market_chains = ["solana", CHAIN]
    settings.chain_max_tokens = 10
    settings.chain_min_liquidity_usd = 50_000.0
    settings.chain_min_volume_usd = 100_000.0
    settings.launchpad_migrations = False
    settings.chain_retain_max_tokens = 0
    settings.chain_watchlist = [f"{CHAIN}:{NAMED}"]
    return settings


AT = datetime(2026, 8, 2, tzinfo=UTC)


# -- collected like anything else -------------------------------------------


async def test_a_named_token_is_measured_without_the_feed(session, watch_settings) -> None:
    market = FakeMarket(snapshot(NAMED), discovers=[])
    report = await collect_chain(
        session,
        settings=watch_settings,
        market=market,
        chain=FakeChain(),
        as_of=AT,
        commit=False,
    )

    assert report.watched == 1
    assert report.as_dict()["watched"] == 1
    token = await session.scalar(select(Token))
    assert token.address == NAMED
    assert token.source == WATCHLIST, "its own frame, not promotion"
    row = await session.scalar(select(TokenSnapshot))
    assert row.selected_by == "watchlist"


async def test_a_named_token_below_the_floors_is_still_measured(
    session, watch_settings
) -> None:
    """The point of naming it. A drained pool is the outcome, not noise."""
    market = FakeMarket(snapshot(NAMED, liquidity=100.0), discovers=[])
    report = await collect_chain(
        session,
        settings=watch_settings,
        market=market,
        chain=FakeChain(),
        as_of=AT,
        commit=False,
    )

    assert report.watched == 1
    assert not any(key.startswith("below_") for key in report.dropped)


async def test_an_address_the_market_does_not_know_is_counted(
    session, watch_settings
) -> None:
    """A wrong address looks exactly like a dead one from here, so it is named
    rather than passed over."""
    watch_settings.chain_watchlist = [f"{CHAIN}:{MISSING}"]
    report = await collect_chain(
        session,
        settings=watch_settings,
        market=FakeMarket(discovers=[]),
        chain=FakeChain(),
        as_of=AT,
        commit=False,
    )

    assert report.watched == 0
    assert report.dropped["watchlist_not_on_market"] == 1


async def test_a_malformed_entry_is_counted_not_ignored(session, watch_settings) -> None:
    watch_settings.chain_watchlist = ["robinhood:", "nonsense"]
    report = await collect_chain(
        session,
        settings=watch_settings,
        market=FakeMarket(discovers=[]),
        chain=FakeChain(),
        as_of=AT,
        commit=False,
    )

    assert report.dropped["watchlist_entry_malformed"] == 2


async def test_naming_a_token_the_feed_already_found_does_not_rewrite_its_frame(
    session, watch_settings
) -> None:
    """How a token entered the dataset is written once.

    Adding it to a list afterwards changes what is measured, never the record
    of how it was found — otherwise every past experiment's population changes
    retroactively and invisibly.
    """
    watch_settings.chain_watchlist = [f"{CHAIN}:{FOUND_BY_FEED}"]
    existing = Token(
        address=FOUND_BY_FEED, chain=CHAIN, symbol="TOK", source=PROMOTED, is_demo=False
    )
    session.add(existing)
    await session.flush()

    await collect_chain(
        session,
        settings=watch_settings,
        market=FakeMarket(snapshot(FOUND_BY_FEED), discovers=[]),
        chain=FakeChain(),
        as_of=AT,
        commit=False,
    )

    await session.refresh(existing)
    assert existing.source == PROMOTED
    row = await session.scalar(select(TokenSnapshot))
    assert row.selected_by == "watchlist", "the row still records why it was taken"


# -- and never compared -----------------------------------------------------


async def test_a_hand_named_token_never_enters_a_dataset(session, watch_settings) -> None:
    """The half that would be easy to skip and impossible to notice.

    A rate computed over a list of tokens somebody picked because they did well
    is a fact about the person who wrote the list.
    """
    template = TEMPLATES[0]
    start = datetime(2026, 8, 1, tzinfo=UTC)
    step = timedelta(minutes=10)
    readings = int((template.window_hours + template.horizon_hours) * 6) + 6

    for address, frame in ((NAMED, WATCHLIST), (FOUND_BY_FEED, PROMOTED)):
        token = Token(
            address=address, chain=CHAIN, symbol="TOK", source=frame, is_demo=False
        )
        session.add(token)
        await session.flush()
        for index in range(readings):
            session.add(
                TokenSnapshot(
                    token_id=token.id,
                    observed_at=start + step * index,
                    liquidity_usd=50_000.0,
                    volume_usd=120_000.0,
                    market_cap_usd=900_000.0,
                    transactions=50,
                    buys=30,
                    sells=20,
                    age_seconds=3_600 * (index + 1),
                    source="live-market-v3",
                    selected_by="watchlist" if frame == WATCHLIST else "discovery",
                    is_demo=False,
                )
            )
    await session.flush()

    dataset = await build_dataset(session, template)

    assert dataset.rows, "the sampled token still produces rows"
    assert all(row.token_address != NAMED for row in dataset.rows)
    assert dataset.excluded.get("hand_selected_token") == 1
