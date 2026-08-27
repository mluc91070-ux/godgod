"""PHASE 8 gate: the Solana and market providers, and the chain collector.

Runs against fake transports. No live node or market API is called — a gate
that depends on a shared public endpoint fails for reasons that have nothing to
do with this codebase.

The check that matters most: `holders` is null on every path. A public RPC node
cannot count holders, and a zero there would flow into the detectors, into the
datasets, and eventually into a published claim.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'ok ' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


async def main() -> int:
    import httpx
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.core.untrusted import CLOSE
    from app.db.session import dispose_engine, get_engine, get_sessionmaker
    from app.models import AgentRun, Base, Token, TokenSnapshot
    from app.providers.base import NotImplementedYet, ProviderNotConfigured
    from app.providers.market import MarketSnapshot, NullMarketProvider, _from_pair
    from app.providers.solana import (
        HolderDistribution,
        HttpSolanaProvider,
        NullSolanaProvider,
        RpcCallFailed,
    )
    from app.providers.source import DatabaseObservationSource
    from app.services.chain import CHAIN_RUN_NAME, collect_chain

    failures = 0
    settings = get_settings()
    settings.demo_mode = False
    settings.chain_min_liquidity_usd = 10_000.0
    settings.chain_min_volume_usd = 25_000.0
    settings.chain_max_tokens = 10
    settings.launchpad_migrations = False
    settings.launchpad_api_url = None
    settings.launchpad_min_liquidity_usd = 1_000.0
    settings.launchpad_min_volume_usd = 25_000.0

    address = "So11111111111111111111111111111111111111112"

    engine = get_engine()
    if engine.url.get_backend_name() == "sqlite":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # -- read only, by construction ---------------------------------------
    methods = {name for name in dir(HttpSolanaProvider) if not name.startswith("_")}
    writes = {"send_transaction", "sign_transaction", "submit_transaction",
              "transfer", "swap", "buy", "sell", "mint", "burn"}
    failures += not check(
        "the chain provider exposes no write path", not (methods & writes)
    )
    failures += not check(
        "every method is a read or a subscription",
        all(
            name.startswith(("get_", "subscribe_")) or name in {"name", "implemented"}
            for name in methods
        ),
    )

    try:
        await NullSolanaProvider().get_account(address)
        failures += not check("an unconfigured node refuses", False)
    except ProviderNotConfigured:
        failures += not check("an unconfigured node refuses", True)

    try:
        await NullMarketProvider().get_snapshot(address)
        failures += not check("an unconfigured market refuses", False)
    except ProviderNotConfigured:
        failures += not check("an unconfigured market refuses", True)

    try:
        NullSolanaProvider().subscribe_logs()
        failures += not check("subscriptions are marked unimplemented", False)
    except NotImplementedYet:
        failures += not check("subscriptions are marked unimplemented", True)

    # -- measurements are measured, or absent ------------------------------
    def pair(liquidity, volume, symbol="TOK"):
        # h1 is what a snapshot stores; h24 only answers "is this traded at all".
        return {
            "chainId": "solana",
            "baseToken": {"address": address, "symbol": symbol, "name": "A Token"},
            "priceUsd": "1.0",
            "liquidity": {"usd": liquidity} if liquidity is not None else {},
            "volume": {"h1": volume, "h24": None if volume is None else volume * 8}
            if volume is not None
            else {},
            "txns": {"h1": {"buys": 3, "sells": 2}},
        }

    folded = _from_pair(address, [pair(30_000.0, 1_000.0), pair(20_000.0, 500.0)])
    failures += not check(
        "liquidity and volume are summed across pools",
        folded.liquidity_usd == 50_000.0 and folded.volume_usd == 1_500.0,
    )
    failures += not check(
        "the stored volume is the hourly window, not the daily one",
        folded.volume_usd == 1_500.0 and folded.volume_24h_usd == 12_000.0,
        "consecutive 24h readings overlap by 96% and hide every spike",
    )
    absent = _from_pair(address, [pair(None, None)])
    failures += not check(
        "an unreported field stays null", absent.liquidity_usd is None
    )
    hostile = _from_pair(address, [pair(1.0, 1.0, symbol=f"OK{CLOSE}")])
    failures += not check(
        "a token symbol cannot forge the untrusted fence", CLOSE not in (hostile.symbol or "")
    )

    # -- the rpc reports throttling rather than absorbing it ---------------
    throttled = HttpSolanaProvider(
        settings if settings.solana_rpc_url else _with_url(settings),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(429, json={}))
        ),
    )
    try:
        await throttled.get_account(address)
        failures += not check("a throttled node raises", False)
    except RpcCallFailed as exc:
        failures += not check("a throttled node raises", "rate-limited" in str(exc))

    # -- the collector ------------------------------------------------------
    class FakeMarket:
        def __init__(self, *snapshots, raises=None):
            self._snapshots = list(snapshots)
            self._raises = raises

        async def discover(self, limit=30):
            if self._raises:
                raise self._raises
            return self._snapshots

        async def search(self, query, limit=20):
            return await self.discover(limit)

        async def get_snapshot(self, addr):
            return next((s for s in self._snapshots if s.address == addr), None)

        async def snapshots(self, addresses):
            wanted = set(addresses)
            return [s for s in self._snapshots if s.address in wanted]

    class FakeChain:
        def __init__(self, top10=0.42, raises=None):
            self._top10 = top10
            self._raises = raises

        async def get_holder_distribution(self, mint):
            if self._raises:
                raise self._raises
            return HolderDistribution(top10_share=self._top10, accounts_seen=20, supply=100.0)

    def measurement(liquidity=50_000.0, volume=120_000.0, volume_24h=None):
        return MarketSnapshot(
            address=address,
            symbol="TOK",
            name="A Token",
            liquidity_usd=liquidity,
            volume_usd=volume,
            volume_24h_usd=volume_24h if volume_24h is not None else volume * 8,
            transactions=5,
            buys=3,
            sells=2,
            created_at=datetime(2026, 8, 1, tzinfo=UTC),
            pairs_seen=1,
        )

    async with get_sessionmaker()() as session:
        stored = await collect_chain(
            session, settings=settings, market=FakeMarket(measurement()), chain=FakeChain(),
            as_of=datetime(2026, 8, 26, 9, tzinfo=UTC),
        )
        failures += not check("a measurement is stored", stored.snapshots_stored == 1)
        failures += not check("the run reports itself complete", stored.as_dict()["complete"])

        rows = (await session.scalars(select(TokenSnapshot))).all()
        failures += not check(
            "holders is null on every stored row",
            bool(rows) and all(row.holders is None for row in rows),
            "a node cannot count holders",
        )
        failures += not check(
            "stored measurements are live data, never demo",
            all(row.is_demo is False for row in rows),
        )

        parked = await collect_chain(
            session,
            settings=settings,
            market=FakeMarket(
                measurement(liquidity=1_800_000_000.0, volume=0.0, volume_24h=102.0)
            ),
            chain=FakeChain(),
            as_of=datetime(2026, 8, 26, 10, tzinfo=UTC),
        )
        failures += not check(
            "a deep pool nobody trades in is dropped",
            parked.snapshots_stored == 0 and "below_volume_floor_promotion" in parked.dropped,
        )

        throttled_run = await collect_chain(
            session,
            settings=settings,
            market=FakeMarket(measurement()),
            chain=FakeChain(raises=RpcCallFailed("the endpoint rate-limited it, twice")),
            as_of=datetime(2026, 8, 26, 11, tzinfo=UTC),
        )
        failures += not check(
            "a throttled distribution costs the field, not the measurement",
            throttled_run.snapshots_stored == 1
            and "holder_distribution_rate_limited" in throttled_run.dropped,
        )

        broken = await collect_chain(
            session,
            settings=settings,
            market=FakeMarket(raises=ProviderNotConfigured("no market")),
            chain=FakeChain(),
            as_of=datetime(2026, 8, 26, 12, tzinfo=UTC),
        )
        failures += not check(
            "an unreachable market makes the run incomplete",
            broken.as_dict()["complete"] is False and broken.error is not None,
        )

        runs = (
            await session.scalars(
                select(AgentRun).where(AgentRun.agent_name == CHAIN_RUN_NAME)
            )
        ).all()
        failures += not check(
            "every run is recorded with no model and no cost",
            bool(runs) and all(r.model is None and r.estimated_cost_usd == 0.0 for r in runs),
            f"{len(runs)} runs",
        )

        # -- the migration frame ------------------------------------------
        from app.providers.launchpad import LaunchpadCallFailed, MigratedToken
        from app.services.chain import MIGRATED, PROMOTED

        class FakeLaunchpad:
            implemented = True

            def __init__(self, *items, raises=None):
                self._items = list(items)
                self._raises = raises

            async def recent_migrations(self, limit=30):
                if self._raises:
                    raise self._raises
                return self._items[:limit]

        mig_address = "MigratedGateAddress1111111111111111111111pump"
        settings.launchpad_migrations = True
        settings.launchpad_api_url = "https://launchpad.example"

        def thin(addr):
            # $6k of liquidity, $343k of volume: measured on a real migration
            # eighteen minutes old. The promotion floor would reject it.
            return MarketSnapshot(
                address=addr,
                symbol="MIG",
                name="A Migrated Token",
                liquidity_usd=6_000.0,
                volume_usd=343_000.0,
                volume_24h_usd=343_000.0,
                transactions=5,
                buys=3,
                sells=2,
            )

        migrated = await collect_chain(
            session,
            settings=settings,
            market=FakeMarket(thin(mig_address)),
            chain=FakeChain(),
            launchpad=FakeLaunchpad(
                MigratedToken(address=mig_address, symbol="MIG", pool="POOL999")
            ),
            as_of=datetime(2026, 8, 26, 9, 0, tzinfo=UTC),
        )
        failures += not check(
            "a thin fresh migration passes the per-frame floor",
            migrated.snapshots_stored == 1 and migrated.migrations_seen == 1,
            f"stored {migrated.snapshots_stored}, seen {migrated.migrations_seen}",
        )

        mig_token = await session.scalar(
            select(Token).where(Token.address == mig_address)
        )
        failures += not check(
            "the sampling frame is recorded on the token",
            mig_token is not None
            and mig_token.source == MIGRATED
            and mig_token.bonding_curve_state == "complete"
            and mig_token.migrated_to_dex == "POOL999",
        )

        promoted_token = await session.scalar(
            select(Token).where(Token.address == address)
        )
        failures += not check(
            "a promoted token is never marked as migrated",
            promoted_token is not None
            and promoted_token.source == PROMOTED
            and promoted_token.bonding_curve_state is None
            and promoted_token.migrated_to_dex is None,
        )

        no_pair = await collect_chain(
            session,
            settings=settings,
            market=FakeMarket(),
            chain=FakeChain(),
            launchpad=FakeLaunchpad(MigratedToken(address="NoPairYet111", symbol="NP")),
            as_of=datetime(2026, 8, 26, 9, 15, tzinfo=UTC),
        )
        failures += not check(
            "a migration with no market pair is counted, not invented",
            no_pair.snapshots_stored == 0
            and no_pair.dropped.get("migration_not_yet_on_market") == 1,
        )

        lp_down = await collect_chain(
            session,
            settings=settings,
            market=FakeMarket(),
            chain=FakeChain(),
            launchpad=FakeLaunchpad(raises=LaunchpadCallFailed("HTTP 530")),
            as_of=datetime(2026, 8, 26, 9, 30, tzinfo=UTC),
        )
        failures += not check(
            "a launchpad failure is reported, not absorbed",
            lp_down.error is None
            and lp_down.launchpad_error is not None
            and lp_down.as_dict()["complete"] is False,
        )

        settings.launchpad_migrations = False
        source = DatabaseObservationSource(session)
        tokens = await source.list_tokens()
        snapshots = await source.get_snapshots(address)
        # Two tokens by now: one from each sampling frame. Both are read back
        # by the same source, which is the point — a migrated token and a
        # promoted one produce identical rows and stay comparable.
        failures += not check(
            "the pipeline can read back what the collector wrote",
            len(tokens) == 2 and len(snapshots) >= 2,
            f"{len(tokens)} tokens, {len(snapshots)} measurements",
        )
        failures += not check(
            "no holder count appears on the way back out",
            all(row["holders"] is None for row in snapshots),
        )

    await dispose_engine()
    print()
    print("PHASE 8 gate:", "PASS" if failures == 0 else f"FAIL ({failures} checks)")
    return 1 if failures else 0


def _with_url(settings):
    settings.solana_rpc_url = "https://rpc.example/gate"
    return settings


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
