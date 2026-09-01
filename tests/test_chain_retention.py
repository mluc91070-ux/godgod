"""Keeping the big ones under measurement, and saying so on every row.

A token used to be measured only while the promotion feed still named it. That
is why the collector held 12,284 readings across 3,732 tokens — 3.3 each,
against a threshold of 6 before any detector may speak. Most of the dataset
never qualified to be looked at.

Retention fixes that, and introduces exactly one thing that could be dishonest:
a second selection rule sharing a column with the first. `selected_by` is what
stops that, and most of this file is about it.

The other half is the floors. A retained token keeps being measured after it
falls through them, because a large cap that drains is the outcome the exposure
was interesting for — dropping it there would be survivorship bias built into
the collector rather than argued for.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select

from app.models import Token, TokenSnapshot
from app.providers.market import MarketSnapshot
from app.services.chain import PROMOTED, collect_chain

BIG = "So11111111111111111111111111111111111111112"
SMALL = "So22222222222222222222222222222222222222222"
OTHER = "0x9F2C82a2b5C40472A3c6Aa3d678C5858345EC71e"
OTHER_CHAIN = "robinhood"
FRESH = "So33333333333333333333333333333333333333333"


def snapshot(
    address: str,
    chain: str = "solana",
    liquidity: float = 50_000.0,
    volume: float = 120_000.0,
    market_cap: float = 9_000_000.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        address=address,
        chain=chain,
        symbol="TOK",
        name="A Token",
        market_cap_usd=market_cap,
        liquidity_usd=liquidity,
        volume_usd=volume,
        volume_24h_usd=None if volume is None else volume * 8,
        transactions=50,
        buys=30,
        sells=20,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


class FakeMarket:
    """Discovery returns only what it was told to; snapshots() answers for any
    address it holds, which is how the retained cohort is fetched."""

    def __init__(self, *snapshots: MarketSnapshot, discovers: list[str] | None = None) -> None:
        self._snapshots = list(snapshots)
        self._discovers = discovers
        self.snapshot_calls: list[tuple[str, tuple[str, ...]]] = []

    async def search(self, query, limit=20):
        return await self.discover(limit)

    async def discover(self, limit=30):
        if self._discovers is None:
            return list(self._snapshots)
        return [item for item in self._snapshots if item.address in self._discovers]

    async def get_snapshot(self, address, chain="solana"):
        return next((s for s in self._snapshots if s.address == address), None)

    async def snapshots(self, addresses, chain="solana"):
        self.snapshot_calls.append((chain, tuple(addresses)))
        wanted = set(addresses)
        return [s for s in self._snapshots if s.address in wanted and s.chain == chain]


class FakeChain:
    async def get_holder_distribution(self, mint):
        from app.providers.solana import HolderDistribution

        return HolderDistribution(top10_share=0.42, accounts_seen=20, supply=1_000.0)


@pytest_asyncio.fixture
async def retain_settings(settings):
    settings.demo_mode = False
    settings.solana_rpc_url = "https://rpc.example/godgod"
    settings.market_api_url = "https://market.example"
    settings.market_chains = ["solana", OTHER_CHAIN]
    settings.chain_max_tokens = 10
    settings.chain_min_liquidity_usd = 10_000.0
    settings.chain_min_volume_usd = 25_000.0
    settings.launchpad_migrations = False
    settings.chain_retain_min_market_cap_usd = 1_000_000.0
    settings.chain_retain_max_tokens = 20
    return settings


async def seed(session, address: str, chain: str, market_cap: float | None) -> Token:
    """One token with one prior measurement, which is what retention reads."""
    token = Token(address=address, chain=chain, symbol="TOK", source=PROMOTED, is_demo=False)
    session.add(token)
    await session.flush()
    session.add(
        TokenSnapshot(
            token_id=token.id,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            market_cap_usd=market_cap,
            liquidity_usd=50_000.0,
            volume_usd=120_000.0,
            source="live-market-v2",
            selected_by="discovery",
            is_demo=False,
        )
    )
    await session.flush()
    return token


LATER = datetime(2026, 8, 2, tzinfo=UTC)


# -- the rule ---------------------------------------------------------------


async def test_a_big_token_is_measured_again_without_the_feed(session, retain_settings) -> None:
    await seed(session, BIG, "solana", 9_000_000.0)
    market = FakeMarket(snapshot(BIG), snapshot(FRESH), discovers=[FRESH])

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 1
    measured = {
        row.address
        for row in (await session.scalars(select(Token))).all()
    }
    assert BIG in measured and FRESH in measured
    rows = (
        await session.scalars(
            select(TokenSnapshot).where(TokenSnapshot.observed_at == LATER)
        )
    ).all()
    assert {row.selected_by for row in rows} == {"retention", "discovery"}


async def test_a_small_token_is_not_retained(session, retain_settings) -> None:
    await seed(session, SMALL, "solana", 40_000.0)
    market = FakeMarket(snapshot(SMALL), discovers=[])

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 0
    assert report.snapshots_stored == 0


async def test_retention_switches_off_cleanly(session, retain_settings) -> None:
    retain_settings.chain_retain_max_tokens = 0
    await seed(session, BIG, "solana", 9_000_000.0)
    market = FakeMarket(snapshot(BIG), discovers=[])

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 0
    assert market.snapshot_calls == []


# -- the floors, and why a retained token skips them ------------------------


async def test_a_drained_token_is_still_measured(session, retain_settings) -> None:
    """The row the discovery floors would delete is the one worth keeping.

    A token that held nine million and now holds a hundred dollars of liquidity
    is not noise to be filtered — it is the outcome that made the earlier
    reading interesting. Dropping it here would be survivorship bias built into
    the collector.
    """
    await seed(session, BIG, "solana", 9_000_000.0)
    drained = snapshot(BIG, liquidity=100.0, volume=5.0, market_cap=2_000.0)
    market = FakeMarket(drained, discovers=[])

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 1
    row = await session.scalar(
        select(TokenSnapshot).where(TokenSnapshot.observed_at == LATER)
    )
    assert row.selected_by == "retention"
    assert row.liquidity_usd == 100.0
    # No floor drop was recorded, because no floor was applied.
    assert not any(key.startswith("below_") for key in report.dropped)


async def test_a_discovered_token_still_faces_the_floors(session, retain_settings) -> None:
    market = FakeMarket(snapshot(FRESH, liquidity=500.0))

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.snapshots_stored == 0
    assert report.dropped == {"below_liquidity_floor_promotion": 1}


async def test_a_retained_token_with_no_pair_is_counted(session, retain_settings) -> None:
    await seed(session, BIG, "solana", 9_000_000.0)
    market = FakeMarket(discovers=[])

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 0
    assert report.dropped["retained_not_on_market"] == 1


# -- per chain, not in total ------------------------------------------------


async def test_each_chain_keeps_its_own_top(session, retain_settings) -> None:
    """In total, the larger caps on one network would fill every slot.

    A budget rule is not allowed to decide which population gets studied.
    """
    retain_settings.chain_retain_max_tokens = 1
    await seed(session, BIG, "solana", 90_000_000.0)
    await seed(session, SMALL, "solana", 9_000_000.0)
    await seed(session, OTHER, OTHER_CHAIN, 2_000_000.0)
    market = FakeMarket(
        snapshot(BIG),
        snapshot(SMALL),
        snapshot(OTHER, chain=OTHER_CHAIN),
        discovers=[],
    )

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 2
    assert report.by_chain == {"solana": 1, OTHER_CHAIN: 1}
    # The largest cap on each chain, not the two largest overall.
    asked = {chain: set(addresses) for chain, addresses in market.snapshot_calls}
    assert asked == {"solana": {BIG}, OTHER_CHAIN: {OTHER}}


async def test_the_cohort_is_ordered_by_market_cap_not_by_insertion(
    session, retain_settings
) -> None:
    retain_settings.chain_retain_max_tokens = 1
    # Seeded smallest first, so insertion order and cap order disagree.
    await seed(session, SMALL, "solana", 2_000_000.0)
    await seed(session, BIG, "solana", 90_000_000.0)
    market = FakeMarket(snapshot(SMALL), snapshot(BIG), discovers=[])

    await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert market.snapshot_calls == [("solana", (BIG,))]


async def test_retention_reads_the_latest_measurement_not_the_first(
    session, retain_settings
) -> None:
    """A token that has fallen below the floor since is no longer retained.

    The rule is about what the token is now, and `Token.market_cap_usd` is a
    cached value with no timestamp on it. Reading the newest snapshot is what
    makes the cohort reconstructible from the dataset.
    """
    token = await seed(session, BIG, "solana", 90_000_000.0)
    session.add(
        TokenSnapshot(
            token_id=token.id,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(hours=1),
            market_cap_usd=1_000.0,
            liquidity_usd=100.0,
            source="live-market-v2",
            selected_by="discovery",
            is_demo=False,
        )
    )
    await session.flush()
    market = FakeMarket(snapshot(BIG), discovers=[])

    report = await collect_chain(
        session,
        settings=retain_settings,
        market=market,
        chain=FakeChain(),
        as_of=LATER,
        commit=False,
    )

    assert report.retained == 0
    assert market.snapshot_calls == []
