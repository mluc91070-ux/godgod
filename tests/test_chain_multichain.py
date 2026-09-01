"""More than one chain in the population, and everything that must not blur.

The promotion feed was never single-chain; the collector was. Removing that
filter adds a second population to the same tables, and these are the four
places where two chains could quietly become one:

- a measurement that does not record which network it came from,
- a Solana RPC asked about an address that is not a Solana mint,
- two different tokens that happen to share an address string, folded together,
- a comparison held within a "liquidity band" that spans both chains.

No live node or market API is called here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from sqlalchemy import select

from app.models import Token, TokenSnapshot
from app.providers.market import HttpMarketProvider, MarketSnapshot, _from_pair
from app.services.chain import PROMOTED, collect_chain
from app.services.research.dataset import build_dataset
from app.services.research.templates import STRATIFICATIONS, TEMPLATES

SOLANA_ADDRESS = "So11111111111111111111111111111111111111112"
OTHER_ADDRESS = "0x9F2C82a2b5C40472A3c6Aa3d678C5858345EC71e"
OTHER_CHAIN = "robinhood"


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def pair(
    address: str, chain: str, liquidity: float = 50_000.0, volume: float = 120_000.0
) -> dict:
    return {
        "chainId": chain,
        "baseToken": {"address": address, "symbol": "TOK", "name": "A Token"},
        "priceUsd": "0.0125",
        "marketCap": 900_000,
        "liquidity": {"usd": liquidity},
        "volume": {"h1": volume, "h24": volume * 8},
        "txns": {"h1": {"buys": 30, "sells": 20}},
        "pairCreatedAt": 1_756_000_000_000,
    }


def snapshot(address: str, chain: str, liquidity: float = 50_000.0) -> MarketSnapshot:
    return MarketSnapshot(
        address=address,
        chain=chain,
        symbol="TOK",
        name="A Token",
        liquidity_usd=liquidity,
        volume_usd=120_000.0,
        volume_24h_usd=960_000.0,
        transactions=50,
        buys=30,
        sells=20,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


class FakeMarket:
    """Answers discover() with whatever it was handed, chains included."""

    def __init__(self, *snapshots: MarketSnapshot) -> None:
        self._snapshots = list(snapshots)

    async def search(self, query, limit=20):
        return self._snapshots

    async def discover(self, limit=30):
        return self._snapshots

    async def get_snapshot(self, address, chain="solana"):
        return next((s for s in self._snapshots if s.address == address), None)

    async def snapshots(self, addresses, chain="solana"):
        wanted = set(addresses)
        return [s for s in self._snapshots if s.address in wanted]


class FakeChain:
    """Records every address the Solana RPC was asked about."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def get_holder_distribution(self, mint):
        from app.providers.solana import HolderDistribution

        self.asked.append(mint)
        return HolderDistribution(top10_share=0.42, accounts_seen=20, supply=1_000.0)


@pytest_asyncio.fixture
async def multichain_settings(settings):
    settings.demo_mode = False
    settings.solana_rpc_url = "https://rpc.example/godgod"
    settings.market_api_url = "https://market.example"
    settings.market_chains = ["solana", OTHER_CHAIN]
    settings.chain_max_tokens = 10
    settings.chain_min_liquidity_usd = 10_000.0
    settings.chain_min_volume_usd = 25_000.0
    settings.launchpad_migrations = False
    return settings


# -- the measurement carries its chain ------------------------------------


def test_a_measurement_records_the_chain_the_source_named() -> None:
    measured = _from_pair(OTHER_ADDRESS, [pair(OTHER_ADDRESS, OTHER_CHAIN)], "solana")
    assert measured is not None
    # Taken from the pair, not from the argument: the source's answer wins.
    assert measured.chain == OTHER_CHAIN


def test_a_measurement_falls_back_to_the_chain_that_was_asked_for() -> None:
    blank = pair(SOLANA_ADDRESS, "solana")
    del blank["chainId"]
    measured = _from_pair(SOLANA_ADDRESS, [blank], "solana")
    assert measured is not None
    assert measured.chain == "solana"


async def test_the_token_row_stores_the_chain_it_was_found_on(
    session, multichain_settings
) -> None:
    await collect_chain(
        session,
        settings=multichain_settings,
        market=FakeMarket(
            snapshot(SOLANA_ADDRESS, "solana"), snapshot(OTHER_ADDRESS, OTHER_CHAIN)
        ),
        chain=FakeChain(),
        commit=False,
    )
    rows = {
        token.address: token.chain for token in (await session.scalars(select(Token))).all()
    }
    assert rows == {SOLANA_ADDRESS: "solana", OTHER_ADDRESS: OTHER_CHAIN}


async def test_the_run_counts_its_measurements_per_chain(session, multichain_settings) -> None:
    report = await collect_chain(
        session,
        settings=multichain_settings,
        market=FakeMarket(
            snapshot(SOLANA_ADDRESS, "solana"), snapshot(OTHER_ADDRESS, OTHER_CHAIN)
        ),
        chain=FakeChain(),
        commit=False,
    )
    assert report.snapshots_stored == 2
    assert report.by_chain == {"solana": 1, OTHER_CHAIN: 1}
    assert report.as_dict()["by_chain"] == {"solana": 1, OTHER_CHAIN: 1}


# -- the Solana node is not asked about other chains ----------------------


async def test_the_solana_rpc_is_never_asked_about_another_chain(
    session, multichain_settings
) -> None:
    """The whole reason the chain is carried on the measurement.

    Asking a Solana node for an EVM address does not fail loudly — it answers
    "no such account", which is indistinguishable from a token nobody holds.
    """
    node = FakeChain()
    report = await collect_chain(
        session,
        settings=multichain_settings,
        market=FakeMarket(
            snapshot(SOLANA_ADDRESS, "solana"), snapshot(OTHER_ADDRESS, OTHER_CHAIN)
        ),
        chain=node,
        commit=False,
    )
    assert node.asked == [SOLANA_ADDRESS]
    assert report.dropped == {"holder_distribution_chain_unsupported": 1}
    assert report.distributions_measured == 1


async def test_the_unmeasured_distribution_is_null_not_zero(
    session, multichain_settings
) -> None:
    await collect_chain(
        session,
        settings=multichain_settings,
        market=FakeMarket(snapshot(OTHER_ADDRESS, OTHER_CHAIN)),
        chain=FakeChain(),
        commit=False,
    )
    row = await session.scalar(select(TokenSnapshot))
    assert row.holder_concentration_top10 is None
    assert row.holders is None


# -- the provider keeps the chains apart ----------------------------------


async def test_discovery_reads_every_configured_chain(multichain_settings) -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "token-boosts" in request.url.path:
            return httpx.Response(
                200,
                json=[
                    {"chainId": "solana", "tokenAddress": SOLANA_ADDRESS},
                    {"chainId": OTHER_CHAIN, "tokenAddress": OTHER_ADDRESS},
                    {"chainId": "ethereum", "tokenAddress": "0xdead"},
                ],
            )
        if f"/tokens/v1/{OTHER_CHAIN}/" in request.url.path:
            return httpx.Response(200, json=[pair(OTHER_ADDRESS, OTHER_CHAIN)])
        return httpx.Response(200, json=[pair(SOLANA_ADDRESS, "solana")])

    provider = HttpMarketProvider(multichain_settings, client=transport(handle))
    found = await provider.discover(limit=10)

    assert {item.chain for item in found} == {"solana", OTHER_CHAIN}
    # One request per chain, and none for a chain nobody configured.
    assert any(f"/tokens/v1/{OTHER_CHAIN}/" in url for url in calls)
    assert not any("/tokens/v1/ethereum/" in url for url in calls)


async def test_the_same_address_on_two_chains_is_two_tokens(multichain_settings) -> None:
    """An address string is only a token together with its network."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "pairs": [
                    pair(OTHER_ADDRESS, "solana", liquidity=10_000.0),
                    pair(OTHER_ADDRESS, OTHER_CHAIN, liquidity=90_000.0),
                ]
            },
        )

    provider = HttpMarketProvider(multichain_settings, client=transport(handle))
    found = await provider.search("tok")

    assert len(found) == 2
    assert {item.chain for item in found} == {"solana", OTHER_CHAIN}
    # Summed within a chain, never across two.
    assert sorted(item.liquidity_usd for item in found) == [10_000.0, 90_000.0]


# -- no comparison spans two chains ---------------------------------------


async def test_every_stratum_names_its_chain(session, multichain_settings) -> None:
    template = TEMPLATES[0]
    start = datetime(2026, 8, 1, tzinfo=UTC)
    step = timedelta(minutes=15)
    readings = int((template.window_hours + template.horizon_hours) * 4) + 4

    for address, chain in ((SOLANA_ADDRESS, "solana"), (OTHER_ADDRESS, OTHER_CHAIN)):
        token = Token(
            address=address, chain=chain, symbol="TOK", source=PROMOTED, is_demo=False
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
                    source="live-market-v2",
                    is_demo=False,
                )
            )
    await session.flush()

    dataset = await build_dataset(session, template)
    assert dataset.rows, "the series is long enough to produce rows"
    strata = {row.stratum for row in dataset.rows}
    # Both chains are present, every stratum names one, and none holds both.
    assert {stratum.split("/")[0] for stratum in strata} == {"solana", OTHER_CHAIN}


def test_every_stratification_label_says_chain() -> None:
    assert all("chain" in label for label in STRATIFICATIONS.values())
    assert all(
        "chain" in (template.variables.get("controls") or []) for template in TEMPLATES
    ), "a comparison held within a chain declares the chain as a control"
