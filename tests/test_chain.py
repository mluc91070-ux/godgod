"""PHASE 8: the Solana provider, the market provider, and the chain collector.

Every request is answered by a fake transport — no live node or market API is
called from the test suite.

The measurement that matters most here is the one that is *not* taken. A public
RPC node cannot supply a holder count, so `holders` must stay null through every
path in this file. A zero there would flow into the detectors, the datasets and
eventually a published claim.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AgentRun, SystemEvent, Token, TokenSnapshot
from app.providers.base import NotImplementedYet, ProviderNotConfigured
from app.providers.market import (
    HttpMarketProvider,
    MarketCallFailed,
    MarketSnapshot,
    NullMarketProvider,
    _from_pair,
)
from app.providers.solana import (
    HttpSolanaProvider,
    NullSolanaProvider,
    RpcCallFailed,
)
from app.providers.source import DatabaseObservationSource
from app.services.chain import CHAIN_RUN_NAME, SNAPSHOT_SOURCE, collect_chain

ADDRESS = "So11111111111111111111111111111111111111112"


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def rpc_responder(result, status: int = 200, error: dict | None = None):
    def handle(request: httpx.Request) -> httpx.Response:
        body = {"jsonrpc": "2.0", "id": 1}
        if error:
            body["error"] = error
        else:
            body["result"] = result
        return httpx.Response(status, json=body)

    return handle


def pair(
    address: str = ADDRESS,
    liquidity: float | None = 50_000.0,
    volume: float | None = 120_000.0,
    buys: int | None = 30,
    sells: int | None = 20,
    symbol: str = "TOK",
) -> dict:
    return {
        "chainId": "solana",
        "baseToken": {"address": address, "symbol": symbol, "name": "A Token"},
        "priceUsd": "0.0125",
        "marketCap": 900_000,
        "liquidity": {"usd": liquidity} if liquidity is not None else {},
        # h1 is what a snapshot stores; h24 only feeds the activity floor.
        "volume": {"h1": volume, "h24": None if volume is None else volume * 8}
        if volume is not None
        else {},
        "txns": {"h1": {"buys": buys, "sells": sells}},
        "pairCreatedAt": 1_756_000_000_000,
    }


@pytest_asyncio.fixture
async def chain_settings(settings):
    settings.demo_mode = False
    settings.solana_rpc_url = "https://rpc.example/godgod"
    settings.market_api_url = "https://market.example"
    settings.chain_watch_queries = ["solana"]
    settings.chain_max_tokens = 10
    settings.chain_min_liquidity_usd = 10_000.0
    settings.chain_min_volume_usd = 25_000.0
    return settings


class FakeMarket:
    def __init__(self, *snapshots: MarketSnapshot, raises: Exception | None = None) -> None:
        self._snapshots = list(snapshots)
        self._raises = raises
        self.queries: list[str] = []

    async def search(self, query, limit=20):
        self.queries.append(query)
        if self._raises:
            raise self._raises
        return self._snapshots

    async def discover(self, limit=30):
        self.queries.append("<discover>")
        if self._raises:
            raise self._raises
        return self._snapshots

    async def get_snapshot(self, address):
        return next((s for s in self._snapshots if s.address == address), None)


class FakeChain:
    def __init__(self, top10: float | None = 0.42, raises: Exception | None = None) -> None:
        self._top10 = top10
        self._raises = raises

    async def get_holder_distribution(self, mint):
        from app.providers.solana import HolderDistribution

        if self._raises:
            raise self._raises
        return HolderDistribution(top10_share=self._top10, accounts_seen=20, supply=1_000.0)


def snapshot(address=ADDRESS, liquidity=50_000.0, volume=120_000.0) -> MarketSnapshot:
    return MarketSnapshot(
        address=address,
        symbol="TOK",
        name="A Token",
        price_usd=0.0125,
        market_cap_usd=900_000.0,
        liquidity_usd=liquidity,
        volume_usd=volume,
        volume_24h_usd=None if volume is None else volume * 8,
        transactions=50,
        buys=30,
        sells=20,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
        pairs_seen=1,
    )


# -- the null providers ---------------------------------------------------


async def test_solana_without_a_url_refuses() -> None:
    with pytest.raises(ProviderNotConfigured, match="SOLANA_RPC_URL"):
        await NullSolanaProvider().get_account(ADDRESS)


async def test_market_without_a_url_refuses() -> None:
    with pytest.raises(ProviderNotConfigured, match="MARKET_API_URL"):
        await NullMarketProvider().get_snapshot(ADDRESS)


def test_subscriptions_are_marked_unimplemented_not_faked() -> None:
    with pytest.raises(NotImplementedYet):
        NullSolanaProvider().subscribe_logs()


def test_the_provider_exposes_no_way_to_send_anything() -> None:
    """V1 is read-only by construction, not by discipline.

    Whole method names, not substrings: `get_signatures` reads signatures and
    contains "sign", and a check that flags it teaches people to ignore it.
    """
    methods = {name for name in dir(HttpSolanaProvider) if not name.startswith("_")}
    writes = {
        "send_transaction",
        "sign_transaction",
        "sign_message",
        "submit_transaction",
        "transfer",
        "swap",
        "buy",
        "sell",
        "mint",
        "burn",
    }
    assert not (methods & writes), f"write path found: {methods & writes}"
    assert all(
        name.startswith(("get_", "subscribe_")) or name in {"name", "implemented"}
        for name in methods
    ), f"a method that is neither a read nor a subscription: {methods}"


# -- the rpc client -------------------------------------------------------


async def test_holder_distribution_is_a_share_of_supply(chain_settings) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        method = request.read().decode()
        if "getTokenLargestAccounts" in method:
            value = [{"uiAmount": 10.0} for _ in range(10)] + [{"uiAmount": 1.0}]
            return httpx.Response(200, json={"result": {"value": value}})
        return httpx.Response(200, json={"result": {"value": {"uiAmount": 200.0}}})

    provider = HttpSolanaProvider(chain_settings, client=transport(handle))
    distribution = await provider.get_holder_distribution(ADDRESS)
    assert distribution.measurable
    assert distribution.top10_share == pytest.approx(0.5)


async def test_an_unreported_supply_makes_the_distribution_unmeasurable(chain_settings):
    def handle(request: httpx.Request) -> httpx.Response:
        if "getTokenLargestAccounts" in request.read().decode():
            return httpx.Response(200, json={"result": {"value": [{"uiAmount": 5.0}]}})
        return httpx.Response(200, json={"result": {"value": {"uiAmount": None}}})

    provider = HttpSolanaProvider(chain_settings, client=transport(handle))
    distribution = await provider.get_holder_distribution(ADDRESS)
    assert distribution.top10_share is None, "unknown, not flat"
    assert distribution.measurable is False


async def test_a_rate_limited_node_says_so(chain_settings) -> None:
    provider = HttpSolanaProvider(
        chain_settings,
        client=transport(lambda request: httpx.Response(429, json={})),
    )
    with pytest.raises(RpcCallFailed, match="rate-limited"):
        await provider.get_account(ADDRESS)


async def test_an_rpc_error_is_raised_not_returned_as_empty(chain_settings) -> None:
    provider = HttpSolanaProvider(
        chain_settings, client=transport(rpc_responder(None, error={"message": "boom"}))
    )
    with pytest.raises(RpcCallFailed, match="boom"):
        await provider.get_account(ADDRESS)


# -- the market client ----------------------------------------------------


def test_liquidity_and_volume_are_summed_across_pools() -> None:
    result = _from_pair(
        ADDRESS,
        [pair(liquidity=30_000.0, volume=1_000.0), pair(liquidity=20_000.0, volume=500.0)],
    )
    assert result.liquidity_usd == pytest.approx(50_000.0)
    assert result.volume_usd == pytest.approx(1_500.0)
    assert result.pairs_seen == 2


def test_price_comes_from_the_deepest_pool_not_an_average() -> None:
    shallow = pair(liquidity=1_000.0)
    shallow["priceUsd"] = "99.0"
    deep = pair(liquidity=100_000.0)
    deep["priceUsd"] = "1.0"
    assert _from_pair(ADDRESS, [shallow, deep]).price_usd == pytest.approx(1.0)


def test_an_unreported_field_stays_none() -> None:
    result = _from_pair(ADDRESS, [pair(liquidity=None, volume=None)])
    assert result.liquidity_usd is None
    assert result.volume_usd is None


def test_a_token_symbol_is_sanitised_because_anyone_can_mint_one() -> None:
    from app.core.untrusted import CLOSE

    hostile = pair(symbol=f"OK{CLOSE}")
    result = _from_pair(ADDRESS, [hostile])
    assert CLOSE not in (result.symbol or "")


def test_pairs_for_other_tokens_are_ignored() -> None:
    assert _from_pair(ADDRESS, [pair(address="OTHER")]) is None


async def test_search_keeps_only_solana_pairs(chain_settings) -> None:
    body = {"pairs": [pair(), {**pair(address="X2"), "chainId": "ethereum"}]}
    provider = HttpMarketProvider(
        chain_settings, client=transport(lambda request: httpx.Response(200, json=body))
    )
    results = await provider.search("solana")
    assert [item.address for item in results] == [ADDRESS]


async def test_a_market_error_is_raised(chain_settings) -> None:
    provider = HttpMarketProvider(
        chain_settings, client=transport(lambda request: httpx.Response(503, text="down"))
    )
    with pytest.raises(MarketCallFailed, match="503"):
        await provider.search("solana")


# -- the collector --------------------------------------------------------


async def test_a_measurement_is_stored_as_live_data(session, chain_settings) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot()),
        chain=FakeChain(),
        commit=False,
    )
    assert report.snapshots_stored == 1
    row = await session.scalar(select(TokenSnapshot).where(TokenSnapshot.source == SNAPSHOT_SOURCE))
    assert row.is_demo is False
    assert row.liquidity_usd == pytest.approx(50_000.0)
    assert row.holder_concentration_top10 == pytest.approx(0.42)


async def test_holders_are_never_invented(session, chain_settings) -> None:
    """The single most important assertion in this file."""
    await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot()),
        chain=FakeChain(),
        commit=False,
    )
    rows = (await session.scalars(select(TokenSnapshot))).all()
    assert rows
    assert all(row.holders is None for row in rows), "a node cannot count holders"


async def test_a_token_below_the_floor_is_dropped_by_name(session, chain_settings) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot(liquidity=500.0)),
        chain=FakeChain(),
        commit=False,
    )
    assert report.snapshots_stored == 0
    assert report.dropped == {"below_liquidity_floor": 1}


async def test_a_token_with_unreported_liquidity_is_dropped_separately(
    session, chain_settings
) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot(liquidity=None)),
        chain=FakeChain(),
        commit=False,
    )
    assert report.dropped == {"liquidity_not_reported": 1}


async def test_a_deep_pool_nobody_trades_in_is_dropped(session, chain_settings) -> None:
    """Measured on the live feed: over a billion dollars of liquidity against a
    hundred dollars of daily volume. That is a parked balance, not a market."""
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot(liquidity=1_800_000_000.0, volume=102.0)),
        chain=FakeChain(),
        commit=False,
    )
    assert report.snapshots_stored == 0
    assert report.dropped == {"below_volume_floor": 1}


async def test_unreported_volume_is_its_own_reason(session, chain_settings) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot(volume=None)),
        chain=FakeChain(),
        commit=False,
    )
    assert report.dropped == {"volume_not_reported": 1}


async def test_the_same_slot_is_not_measured_twice(session, chain_settings) -> None:
    at = datetime(2026, 8, 26, 12, tzinfo=UTC)
    first = await collect_chain(
        session, settings=chain_settings, market=FakeMarket(snapshot()),
        chain=FakeChain(), as_of=at, commit=False,
    )
    second = await collect_chain(
        session, settings=chain_settings, market=FakeMarket(snapshot()),
        chain=FakeChain(), as_of=at, commit=False,
    )
    assert first.snapshots_stored == 1
    assert second.snapshots_stored == 0
    assert second.dropped["already_measured_this_slot"] == 1


async def test_a_failing_rpc_costs_the_distribution_not_the_measurement(
    session, chain_settings
) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot()),
        chain=FakeChain(raises=RpcCallFailed("node down")),
        commit=False,
    )
    assert report.snapshots_stored == 1
    assert report.dropped["holder_distribution_failed"] == 1
    row = await session.scalar(select(TokenSnapshot))
    assert row.holder_concentration_top10 is None
    assert row.liquidity_usd is not None, "the market measurement survived"


async def test_a_throttled_rpc_is_named_differently_from_a_broken_one(
    session, chain_settings
) -> None:
    """The fix differs: a throttled endpoint needs a dedicated RPC url, a
    broken one needs looking at. A single reason would hide that."""
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot()),
        chain=FakeChain(raises=RpcCallFailed("the RPC endpoint rate-limited it, twice")),
        commit=False,
    )
    assert report.dropped["holder_distribution_rate_limited"] == 1
    assert report.snapshots_stored == 1, "the measurement is still worth storing"


async def test_an_unmeasurable_distribution_is_recorded_as_such(
    session, chain_settings
) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(snapshot()),
        chain=FakeChain(top10=None),
        commit=False,
    )
    assert report.distributions_measured == 0
    assert report.dropped["holder_distribution_not_reported"] == 1


async def test_an_unreachable_market_makes_the_run_incomplete(session, chain_settings) -> None:
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(raises=MarketCallFailed("down")),
        chain=FakeChain(),
        commit=False,
    )
    assert report.error is not None
    assert report.as_dict()["complete"] is False


async def test_the_run_is_recorded_with_no_model_and_no_cost(session, chain_settings) -> None:
    await collect_chain(
        session, settings=chain_settings, market=FakeMarket(snapshot()),
        chain=FakeChain(), commit=False,
    )
    run = await session.scalar(select(AgentRun).where(AgentRun.agent_name == CHAIN_RUN_NAME))
    assert run.model is None and run.estimated_cost_usd == 0.0
    event = await session.scalar(
        select(SystemEvent).where(SystemEvent.ref_type == "chain-collector")
    )
    assert event.is_demo is False


# -- the live source ------------------------------------------------------


async def test_the_live_source_reads_back_what_the_collector_wrote(
    session, chain_settings
) -> None:
    for hour in range(3):
        await collect_chain(
            session,
            settings=chain_settings,
            market=FakeMarket(snapshot()),
            chain=FakeChain(),
            as_of=datetime(2026, 8, 26, 10 + hour, tzinfo=UTC),
            commit=False,
        )

    source = DatabaseObservationSource(session)
    tokens = await source.list_tokens()
    assert [t.address for t in tokens] == [ADDRESS]

    rows = await source.get_snapshots(ADDRESS)
    assert len(rows) == 3
    assert [r["observed_at"].hour for r in rows] == [10, 11, 12]
    assert all(r["holders"] is None for r in rows)

    latest = await source.latest_timestamp()
    assert latest.hour == 12


async def test_the_live_source_never_serves_demo_rows(session, chain_settings, seeded) -> None:
    """Demo and live data are separated at the row level, not by convention."""
    await collect_chain(
        session, settings=chain_settings, market=FakeMarket(snapshot()),
        chain=FakeChain(), commit=False,
    )
    addresses = {t.address for t in await DatabaseObservationSource(session).list_tokens()}
    demo = {
        row.address
        for row in (await session.scalars(select(Token).where(Token.is_demo.is_(True)))).all()
    }
    assert addresses == {ADDRESS}
    assert not (addresses & demo)


async def test_the_source_choice_follows_demo_mode(session, settings) -> None:
    from app.providers.source import FixtureObservationSource, get_observation_source

    settings.demo_mode = True
    demo_source = get_observation_source(session=session, settings=settings)
    assert isinstance(demo_source, FixtureObservationSource)

    settings.demo_mode = False
    live_source = get_observation_source(session=session, settings=settings)
    assert isinstance(live_source, DatabaseObservationSource)


async def test_without_a_session_the_fixture_source_is_returned(settings) -> None:
    """Serving fixtures to a production pipeline would mix demo and real data,
    so the caller must supply a session to get the live one."""
    from app.providers.source import FixtureObservationSource, get_observation_source

    settings.demo_mode = False
    assert isinstance(get_observation_source(settings=settings), FixtureObservationSource)


# -- the endpoints --------------------------------------------------------


async def test_the_chain_endpoint_requires_the_operator_token(client) -> None:
    assert (await client.post("/api/admin/chain/collect")).status_code in (401, 403)


async def test_the_chain_endpoint_reports_an_unconfigured_market(client, admin_headers) -> None:
    response = await client.post("/api/admin/chain/collect", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["complete"] is False
    assert "MARKET_API_URL" in (body["error"] or "")


async def test_status_reports_solana_and_market_honestly(client) -> None:
    providers = {p["name"]: p for p in (await client.get("/api/status")).json()["providers"]}
    assert providers["solana"]["implemented"] is True
    assert providers["solana"]["configured"] is False
    assert "no signing path" in providers["solana"]["note"].lower()
    assert providers["market"]["implemented"] is True
    assert providers["market"]["configured"] is False


# -- going live -----------------------------------------------------------


async def test_go_live_requires_the_operator_token(client) -> None:
    assert (await client.post("/api/admin/go-live")).status_code in (401, 403)


async def test_go_live_refuses_before_there_is_history(client, admin_headers) -> None:
    body = (await client.post("/api/admin/go-live", headers=admin_headers)).json()
    assert body["ready"] is False
    assert body["deleted"] is False
    assert "measurements yet" in body["note"]


async def test_go_live_does_not_delete_without_confirmation(
    session, client, admin_headers, chain_settings
) -> None:
    from app.models import Token as TokenModel

    for hour in range(6):
        await collect_chain(
            session,
            settings=chain_settings,
            market=FakeMarket(snapshot()),
            chain=FakeChain(),
            as_of=datetime(2026, 8, 26, 8 + hour, tzinfo=UTC),
        )

    body = (await client.post("/api/admin/go-live", headers=admin_headers)).json()
    assert body["ready"] is True
    assert body["deleted"] is False
    assert body["ready_tokens"] == ["TOK"]

    demo = (await session.scalars(select(TokenModel).where(TokenModel.is_demo.is_(True)))).all()
    assert demo, "the demo rows are still there"


async def test_go_live_deletes_demo_rows_but_does_not_flip_the_mode(
    session, client, admin_headers, chain_settings
) -> None:
    """Deleting rows is not the same act as changing the environment, and the
    response must not imply the site is live when it is not."""
    from app.models import Token as TokenModel

    for hour in range(6):
        await collect_chain(
            session,
            settings=chain_settings,
            market=FakeMarket(snapshot()),
            chain=FakeChain(),
            as_of=datetime(2026, 8, 26, 8 + hour, tzinfo=UTC),
        )

    body = (
        await client.post(
            "/api/admin/go-live", params={"confirm": "true"}, headers=admin_headers
        )
    ).json()
    assert body["deleted"] is True
    assert "DEMO_MODE=false" in body["note"]

    demo = (await session.scalars(select(TokenModel).where(TokenModel.is_demo.is_(True)))).all()
    assert not demo

    live = (await session.scalars(select(TokenModel).where(TokenModel.is_demo.is_(False)))).all()
    assert live, "the real measurements survived"


# -- the measurement matches the cadence ----------------------------------


def test_volume_is_the_hourly_figure_not_the_daily_one() -> None:
    """Snapshots are hourly. Two consecutive readings of a 24h rolling volume
    overlap by 96%, so a spike is smeared across a day and the detector looking
    for one never sees it. The window has to match the sampling rate."""
    p = pair()
    p["volume"] = {"h24": 240_000.0, "h6": 60_000.0, "h1": 10_000.0}
    p["txns"] = {"h24": {"buys": 900, "sells": 300}, "h1": {"buys": 40, "sells": 12}}

    result = _from_pair(ADDRESS, [p])
    assert result.volume_usd == pytest.approx(10_000.0), "hourly volume"
    assert result.volume_24h_usd == pytest.approx(240_000.0), "daily kept for the floor"
    assert result.buys == 40
    assert result.sells == 12
    assert result.transactions == 52


async def test_the_activity_floor_uses_the_daily_figure(session, chain_settings) -> None:
    """'Is this token traded at all' is a question about the token, not about
    this particular hour. A quiet hour must not evict an active token."""
    quiet_hour = MarketSnapshot(
        address=ADDRESS,
        symbol="TOK",
        liquidity_usd=50_000.0,
        volume_usd=40.0,
        volume_24h_usd=500_000.0,
        transactions=2,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    report = await collect_chain(
        session,
        settings=chain_settings,
        market=FakeMarket(quiet_hour),
        chain=FakeChain(),
        commit=False,
    )
    assert report.snapshots_stored == 1, "a quiet hour on an active token is still a row"
    row = await session.scalar(select(TokenSnapshot))
    assert row.volume_usd == pytest.approx(40.0)


async def test_a_token_nobody_trades_is_still_dropped(session, chain_settings) -> None:
    dead = MarketSnapshot(
        address=ADDRESS,
        symbol="DEAD",
        liquidity_usd=1_800_000_000.0,
        volume_usd=0.0,
        volume_24h_usd=102.0,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    report = await collect_chain(
        session, settings=chain_settings, market=FakeMarket(dead),
        chain=FakeChain(), commit=False,
    )
    assert report.dropped == {"below_volume_floor": 1}
