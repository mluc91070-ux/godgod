"""The migration frame, inside the collector.

Two populations enter the same table, and the whole value of that depends on
being able to tell them apart afterwards. If `Token.source` is wrong, every
experiment that stratifies on the sampling frame is quietly wrong too, and
nothing downstream can detect it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from tests.test_chain import FakeChain, FakeMarket

from app.models import Token
from app.providers.base import ProviderNotConfigured
from app.providers.launchpad import LaunchpadCallFailed, MigratedToken
from app.providers.market import MarketSnapshot
from app.services.chain import MIGRATED, PROMOTED, collect_chain

PROMOTED_ADDRESS = "PromotedTokenAddress11111111111111111111111"
MIGRATED_ADDRESS = "MigratedTokenAddress111111111111111111111pump"


def market_snapshot(address: str, liquidity: float, volume: float) -> MarketSnapshot:
    return MarketSnapshot(
        address=address,
        symbol="TOK",
        name="a token",
        liquidity_usd=liquidity,
        volume_usd=volume,
        volume_24h_usd=volume,
        transactions=50,
        buys=30,
        sells=20,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def migration(address: str = MIGRATED_ADDRESS, pool: str | None = "POOL999") -> MigratedToken:
    return MigratedToken(
        address=address,
        symbol="MIG",
        name="a migrated token",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        pool=pool,
        market_cap_usd=91_000.0,
    )


class FakeLaunchpad:
    implemented = True

    def __init__(self, *migrations: MigratedToken, raises: Exception | None = None) -> None:
        self._migrations = list(migrations)
        self._raises = raises
        self.calls = 0

    async def recent_migrations(self, limit: int = 30):
        self.calls += 1
        if self._raises:
            raise self._raises
        return self._migrations[:limit]


@pytest_asyncio.fixture
async def migration_settings(settings):
    settings.demo_mode = False
    settings.solana_rpc_url = "https://rpc.example/godgod"
    settings.market_api_url = "https://market.example"
    settings.chain_max_tokens = 10
    settings.chain_min_liquidity_usd = 10_000.0
    settings.chain_min_volume_usd = 25_000.0
    settings.launchpad_migrations = True
    settings.launchpad_api_url = "https://launchpad.example"
    settings.launchpad_max_tokens = 10
    settings.launchpad_min_liquidity_usd = 1_000.0
    settings.launchpad_min_volume_usd = 25_000.0
    return settings


async def test_a_migrated_token_records_the_frame_that_found_it(
    session, migration_settings
) -> None:
    market = FakeMarket(
        market_snapshot(PROMOTED_ADDRESS, 50_000.0, 120_000.0),
        market_snapshot(MIGRATED_ADDRESS, 21_000.0, 200_000.0),
    )
    # discover() returns only the promoted one; the migrated one arrives
    # through the launchpad and is measured by snapshots().
    market.discover = lambda limit=30: _only(market, PROMOTED_ADDRESS)

    report = await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(migration()),
    )

    assert report.migrations_seen == 1
    assert report.migrations_measured == 1
    assert report.snapshots_stored == 2

    tokens = {t.address: t for t in (await session.scalars(select(Token))).all()}
    assert tokens[PROMOTED_ADDRESS].source == PROMOTED
    assert tokens[MIGRATED_ADDRESS].source == MIGRATED
    assert tokens[MIGRATED_ADDRESS].bonding_curve_state == "complete"
    assert tokens[MIGRATED_ADDRESS].migrated_to_dex == "POOL999"
    # The promoted token was never claimed to have migrated.
    assert tokens[PROMOTED_ADDRESS].bonding_curve_state is None
    assert tokens[PROMOTED_ADDRESS].migrated_to_dex is None


async def _only(market, address):
    return [s for s in market._snapshots if s.address == address]


async def test_a_migration_without_a_pool_leaves_the_field_null(
    session, migration_settings
) -> None:
    """No key in the payload, no destination on the record."""
    market = FakeMarket(market_snapshot(MIGRATED_ADDRESS, 21_000.0, 200_000.0))
    market.discover = lambda limit=30: _only(market, "nothing")

    await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(migration(pool=None)),
    )

    token = await session.scalar(select(Token).where(Token.address == MIGRATED_ADDRESS))
    assert token is not None
    assert token.bonding_curve_state == "complete"
    assert token.migrated_to_dex is None


async def test_a_thin_fresh_migration_survives_the_promotion_floor(
    session, migration_settings
) -> None:
    """The floors are per-frame, and this is the case that made them so.

    Measured live: a token eighteen minutes past migration trading $343k in an
    hour on a $6k pool. The promotion feed's $10k floor exists to reject a deep
    pool nobody trades; applied here it rejects the opposite thing.
    """
    market = FakeMarket(market_snapshot(MIGRATED_ADDRESS, 6_000.0, 343_000.0))
    market.discover = lambda limit=30: _only(market, "nothing")

    report = await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(migration()),
    )

    assert report.snapshots_stored == 1
    assert "below_liquidity_floor_migration" not in report.dropped


async def test_the_same_thin_token_is_dropped_when_only_promoted(
    session, migration_settings
) -> None:
    """The other half of the previous test: the floor still does its job."""
    market = FakeMarket(market_snapshot(PROMOTED_ADDRESS, 6_000.0, 343_000.0))

    report = await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(),
    )

    assert report.snapshots_stored == 0
    assert report.dropped["below_liquidity_floor_promotion"] == 1


async def test_a_migration_with_no_market_pair_yet_is_counted_not_invented(
    session, migration_settings
) -> None:
    """Absent from the market is a real state, not zero liquidity."""
    market = FakeMarket()

    report = await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(migration()),
    )

    assert report.migrations_seen == 1
    assert report.migrations_measured == 0
    assert report.dropped["migration_not_yet_on_market"] == 1
    assert report.snapshots_stored == 0


async def test_a_launchpad_failure_does_not_fail_the_run(
    session, migration_settings
) -> None:
    """One frame down is not a failed run — but the run says so."""
    market = FakeMarket(market_snapshot(PROMOTED_ADDRESS, 50_000.0, 120_000.0))

    report = await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(raises=LaunchpadCallFailed("HTTP 530")),
    )

    assert report.snapshots_stored == 1  # the promotion frame still worked
    assert report.error is None
    assert "LaunchpadCallFailed" in (report.launchpad_error or "")
    # A run that lost a population is not a complete run.
    assert report.as_dict()["complete"] is False


async def test_an_unconfigured_launchpad_is_recorded_not_silent(
    session, migration_settings
) -> None:
    """Looked-at-nothing must never look like found-nothing."""
    migration_settings.launchpad_api_url = None
    market = FakeMarket(market_snapshot(PROMOTED_ADDRESS, 50_000.0, 120_000.0))

    class Unconfigured:
        implemented = False

        async def recent_migrations(self, limit: int = 30):
            raise ProviderNotConfigured("LAUNCHPAD_API_URL is not set")

    report = await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=Unconfigured(),
    )

    assert report.dropped["launchpad_not_configured"] == 1
    assert report.migrations_seen == 0
    # Not configured is a decision, so the run is still complete.
    assert report.as_dict()["complete"] is True


@pytest.mark.parametrize("enabled", [True, False])
async def test_the_frame_is_never_rewritten_on_a_later_run(
    session, migration_settings, enabled
) -> None:
    """A token that entered as promoted stays promoted.

    Rewriting it would change the population of every experiment already run
    against it, retroactively and invisibly.
    """
    market = FakeMarket(market_snapshot(MIGRATED_ADDRESS, 21_000.0, 200_000.0))

    # First run: found by the promotion feed.
    await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(),
    )

    # Second run: the launchpad now reports it as migrated.
    migration_settings.launchpad_migrations = enabled
    await collect_chain(
        session,
        settings=migration_settings,
        market=market,
        chain=FakeChain(),
        launchpad=FakeLaunchpad(migration()),
        as_of=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    )

    token = await session.scalar(select(Token).where(Token.address == MIGRATED_ADDRESS))
    assert token is not None
    assert token.source == PROMOTED
    # The curve fact is still recorded — it is a fact about the token, not
    # about which frame sampled it.
    assert token.bonding_curve_state == ("complete" if enabled else None)
