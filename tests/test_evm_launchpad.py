"""Reading a bonding curve off a chain instead of asking an API for it.

No node is called here. What is exercised is every place the reader could
invent a fact it was not given, because that is the only interesting failure
mode: an API that goes down returns an error, but a contract that does not
implement a function *reverts*, and a revert read as `false` becomes a token
recorded as still on its curve when nothing ever checked.

That case is not hypothetical. Two contracts on this chain emit the same launch
event and only one of them answers the follow-up call.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

from app.core.keccak import event_topic, function_selector
from app.models import ChainCursor, LaunchpadLaunch
from app.providers.base import ProviderNotConfigured
from app.providers.evm import (
    EvmCallFailed,
    EvmReverted,
    HttpEvmProvider,
    NullEvmProvider,
    address_from_topic,
    encode_address_arg,
    words,
)
from app.providers.launchpad import (
    EvmLaunchpadProvider,
    LaunchpadCallFailed,
    NullLaunchpadProvider,
    get_launchpad_provider,
    reset_launchpad_provider,
)
from app.services.launchpad_scan import scan_launchpad

FACTORY = "0x2cdddb0fd8d9295e10a65b943113cea6b9328414"
OTHER_FACTORY = "0x52453b4289a6c3a70bb8b4682bcd3d8731267e28"
TOKEN_A = "0x522f35cee3efbc492dc0973e22e23824951fb097"
TOKEN_B = "0x489cfd5f13877f02052dd48cb08c7a3e94f0f2b5"
TOKEN_C = "0xeaafb801220ffd823b538fb1702354ad3b7ad062"

LAUNCH_EVENT = (
    "TokenLaunched(address,address,address,address,address,"
    "uint256,uint256,uint256,uint256,uint256)"
)


def word(value: int) -> str:
    return f"{value:064x}"


def log(token: str, factory: str = FACTORY, block: int = 51_999_000) -> dict:
    return {
        "address": factory,
        "blockNumber": hex(block),
        "topics": [
            event_topic(LAUNCH_EVENT),
            "0x" + token[2:].rjust(64, "0"),
            "0x" + "1" * 64,
            "0x" + "2" * 64,
        ],
        "data": "0x" + word(0) * 7,
    }


def status(graduated: bool, principal: int = 5, threshold: int = 42) -> str:
    return "0x" + word(principal) + word(threshold) + word(1 if graduated else 0)


class FakeEvm:
    """Answers what it was handed, and records what it was asked."""

    def __init__(
        self,
        *,
        logs: list[dict] | None = None,
        answers: dict[str, str] | None = None,
        reverts: set[str] | None = None,
        chain: int = 4663,
    ) -> None:
        self._logs = logs or []
        self._answers = answers or {}
        self._reverts = reverts or set()
        self._chain = chain
        self.calls: list[str] = []
        self.log_queries: list[dict] = []

    async def chain_id(self) -> int:
        return self._chain

    async def block_number(self) -> int:
        return 52_000_000

    async def get_logs(self, *, from_block, to_block, topics=None, address=None):
        self.log_queries.append(
            {"from": from_block, "to": to_block, "topics": topics, "address": address}
        )
        if to_block - from_block + 1 > 2_000:
            # What the live node does, so a test cannot pass on a range it
            # would refuse: "only allowed to search 2000 blocks per request".
            raise EvmCallFailed("only allowed to search 2000 blocks per request")
        return [
            entry
            for entry in self._logs
            if from_block <= int(str(entry.get("blockNumber", "0x0")), 16) <= to_block
        ]

    async def call(self, to: str, data: str) -> str:
        token = "0x" + data[-40:]
        self.calls.append(token)
        if token in self._reverts:
            raise EvmReverted("execution reverted")
        return self._answers.get(token, "0x")


@pytest_asyncio.fixture
async def evm_settings(settings):
    settings.evm_rpc_url = "https://node.example/rpc"
    settings.evm_chain = "robinhood"
    settings.evm_chain_id = 4663
    settings.evm_launchpad_factories = [FACTORY]
    settings.evm_launchpad_max_calls = 40
    settings.evm_retries = 1
    settings.evm_retry_seconds = 0.0
    reset_launchpad_provider()
    yield settings
    reset_launchpad_provider()


# -- decoding helpers -------------------------------------------------------


def test_an_indexed_address_is_the_low_twenty_bytes() -> None:
    assert address_from_topic("0x" + TOKEN_A[2:].rjust(64, "0")) == TOKEN_A


def test_an_address_argument_is_padded_to_a_word() -> None:
    encoded = encode_address_arg(TOKEN_A)
    assert len(encoded) == 64
    assert encoded.endswith(TOKEN_A[2:])


def test_return_data_splits_into_words() -> None:
    assert words(status(True)) == [word(5), word(42), word(1)]
    assert words("0x") == []


# -- the node client --------------------------------------------------------


def transport(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def responder(result):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    return handle


async def test_the_client_parses_hex_answers(evm_settings) -> None:
    provider = HttpEvmProvider(evm_settings, client=transport(responder("0x1237")))
    assert await provider.chain_id() == 4663


async def test_a_revert_is_its_own_failure(evm_settings) -> None:
    """The whole reason this class exists.

    A revert means the contract has no answer. Folded into a generic error it
    would be retried; read as a value it would become a measurement nobody
    took.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": 3, "message": "execution reverted"}},
        )

    provider = HttpEvmProvider(evm_settings, client=transport(handle))
    with pytest.raises(EvmReverted):
        await provider.call(FACTORY, "0xdeadbeef")


async def test_a_rate_limited_node_is_named(evm_settings) -> None:
    """Measured on the live endpoint: a burst of reads returns 429."""
    seen: list[int] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(429, text="slow down")

    provider = HttpEvmProvider(evm_settings, client=transport(handle))
    with pytest.raises(EvmCallFailed, match="rate-limited"):
        await provider.block_number()
    assert len(seen) == 2, "one retry, then it gives up rather than hammering"


async def test_an_unconfigured_node_refuses() -> None:
    with pytest.raises(ProviderNotConfigured, match="EVM_RPC_URL"):
        await NullEvmProvider().block_number()


# -- the launchpad reader ---------------------------------------------------


async def test_a_wide_range_is_split_not_truncated(evm_settings) -> None:
    """The node caps a log query at two thousand blocks.

    Reading only the last two thousand of a six-thousand block request would
    report a launchpad where almost nothing happens, and nothing would say so.
    """
    evm = FakeEvm(logs=[log(TOKEN_A, block=51_995_100), log(TOKEN_B, block=51_999_900)])
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    found = await provider.scan_launches(51_994_001, 52_000_000)

    assert len(evm.log_queries) == 3
    assert all(q["to"] - q["from"] + 1 <= 2_000 for q in evm.log_queries)
    # Both ends of the range are covered, not just the last chunk.
    assert {item.address for item in found} == {TOKEN_A, TOKEN_B}


async def test_logs_from_an_unconfigured_factory_are_ignored(evm_settings) -> None:
    """The topic is not unique to one contract, so the address decides."""
    evm = FakeEvm(logs=[log(TOKEN_A, OTHER_FACTORY)])
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    assert await provider.scan_launches(51_999_000, 51_999_500) == []


async def test_the_scan_filters_by_topic_not_by_address(evm_settings) -> None:
    """A node that quietly ignored an address filter would hand back another
    contract's launches as this one's. The addresses are checked here."""
    evm = FakeEvm(logs=[])
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)
    await provider.scan_launches(51_999_000, 51_999_500)

    assert evm.log_queries[0]["topics"] == [event_topic(LAUNCH_EVENT)]
    assert evm.log_queries[0]["address"] is None


async def test_a_revert_is_unreadable_not_a_no(evm_settings) -> None:
    """The whole reason the status is three-valued.

    Measured on this chain: the same launch event is emitted by a second
    contract that has no status view at all, and asking it reverts.
    """
    evm = FakeEvm(answers={TOKEN_B: status(True)}, reverts={TOKEN_A})
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    assert await provider.graduation_status(FACTORY, TOKEN_A) is None
    assert await provider.graduation_status(FACTORY, TOKEN_B) is True
    assert await provider.graduation_status(FACTORY, TOKEN_C) is None


async def test_a_node_on_the_wrong_chain_refuses(evm_settings) -> None:
    evm = FakeEvm(chain=1)
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)
    with pytest.raises(LaunchpadCallFailed, match="chain id 1"):
        await provider.head_block()


async def test_the_one_shot_query_refuses_rather_than_returning_nothing(
    evm_settings,
) -> None:
    """A chain cannot answer "what migrated recently" in one call.

    An empty list here would be read as a launchpad where nothing graduates.
    """
    provider = EvmLaunchpadProvider(evm_settings, evm=FakeEvm())
    with pytest.raises(LaunchpadCallFailed, match="scanned incrementally"):
        await provider.recent_migrations()


async def test_an_unset_factory_list_yields_a_provider_that_says_so(evm_settings) -> None:
    evm_settings.evm_launchpad_factories = []
    provider = get_launchpad_provider(evm_settings, "robinhood")

    assert isinstance(provider, NullLaunchpadProvider)
    assert provider.implemented is False


def test_the_selector_is_derived_from_the_signature(evm_settings) -> None:
    """The config holds a readable signature; the wire gets its hash."""
    assert function_selector(evm_settings.evm_launchpad_status_call) == "0x98d652f1"


# -- the scan, which owns the cursor ----------------------------------------


async def test_the_first_scan_starts_near_the_head(session, evm_settings) -> None:
    """Not at the launchpad's first block.

    That would be hundreds of requests before the first useful answer. What was
    never scanned is not claimed, and the cursor records where the edge is.
    """
    evm_settings.evm_scan_start_blocks_back = 5_000
    evm_settings.evm_scan_max_blocks_per_run = 6_000
    provider = EvmLaunchpadProvider(evm_settings, evm=FakeEvm())

    result = await scan_launchpad(session, settings=evm_settings, provider=provider)

    assert result.report.from_block == 52_000_000 - 5_000
    cursor = await session.scalar(select_cursor())
    assert cursor is not None and cursor.block == 52_000_000


async def test_the_cursor_advances_and_does_not_re_read(session, evm_settings) -> None:
    evm_settings.evm_scan_start_blocks_back = 3_000
    evm_settings.evm_scan_max_blocks_per_run = 2_000
    provider = EvmLaunchpadProvider(evm_settings, evm=FakeEvm())

    first = await scan_launchpad(session, settings=evm_settings, provider=provider)
    second = await scan_launchpad(session, settings=evm_settings, provider=provider)

    assert second.report.from_block == first.report.to_block + 1
    assert second.report.behind_blocks < first.report.behind_blocks


async def test_a_failed_scan_leaves_the_cursor_where_it_was(session, evm_settings) -> None:
    """A gap stepped over is indistinguishable from a quiet launchpad."""

    class Failing(FakeEvm):
        async def get_logs(self, **kwargs):
            raise EvmCallFailed("the node rate-limited eth_getLogs")

    evm_settings.evm_scan_max_blocks_per_run = 2_000
    ok = EvmLaunchpadProvider(evm_settings, evm=FakeEvm())
    await scan_launchpad(session, settings=evm_settings, provider=ok)
    before = (await session.scalar(select_cursor())).block

    broken = EvmLaunchpadProvider(evm_settings, evm=Failing())
    result = await scan_launchpad(session, settings=evm_settings, provider=broken)

    assert result.report.error is not None
    assert (await session.scalar(select_cursor())).block == before


async def test_a_launch_is_recorded_before_it_is_resolved(session, evm_settings) -> None:
    evm_settings.evm_scan_start_blocks_back = 2_000
    evm_settings.evm_scan_max_blocks_per_run = 2_000
    evm = FakeEvm(
        logs=[log(TOKEN_A, block=51_999_000)], answers={TOKEN_A: status(False)}
    )
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    result = await scan_launchpad(session, settings=evm_settings, provider=provider)

    assert result.report.launches_new == 1
    assert result.migrations == []
    row = await session.scalar(select_launch(TOKEN_A))
    assert row is not None
    assert row.graduated is False, "asked and answered"
    assert row.graduated_at is None


async def test_a_graduated_curve_becomes_a_migration(session, evm_settings) -> None:
    evm_settings.evm_scan_start_blocks_back = 2_000
    evm_settings.evm_scan_max_blocks_per_run = 2_000
    evm = FakeEvm(logs=[log(TOKEN_A, block=51_999_000)], answers={TOKEN_A: status(True)})
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    result = await scan_launchpad(session, settings=evm_settings, provider=provider)

    assert [item.address for item in result.migrations] == [TOKEN_A]
    row = await session.scalar(select_launch(TOKEN_A))
    assert row.graduated is True
    assert row.graduated_at is not None


async def test_a_curve_that_finishes_later_is_caught_on_a_later_pass(
    session, evm_settings
) -> None:
    """The reason the table exists.

    The launch and the graduation are hours apart, so a windowed scan that only
    looked at fresh logs would never see the second half.
    """
    evm_settings.evm_scan_start_blocks_back = 2_000
    evm_settings.evm_scan_max_blocks_per_run = 2_000
    still_running = FakeEvm(
        logs=[log(TOKEN_A, block=51_999_000)], answers={TOKEN_A: status(False)}
    )
    first = await scan_launchpad(
        session,
        settings=evm_settings,
        provider=EvmLaunchpadProvider(evm_settings, evm=still_running),
    )
    assert first.migrations == []

    finished = FakeEvm(logs=[], answers={TOKEN_A: status(True)})
    second = await scan_launchpad(
        session,
        settings=evm_settings,
        provider=EvmLaunchpadProvider(evm_settings, evm=finished),
    )

    assert [item.address for item in second.migrations] == [TOKEN_A]


async def test_a_reverting_contract_leaves_the_row_unknown(session, evm_settings) -> None:
    evm_settings.evm_scan_start_blocks_back = 2_000
    evm_settings.evm_scan_max_blocks_per_run = 2_000
    evm = FakeEvm(logs=[log(TOKEN_A, block=51_999_000)], reverts={TOKEN_A})
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    result = await scan_launchpad(session, settings=evm_settings, provider=provider)

    assert result.report.unreadable == 1
    row = await session.scalar(select_launch(TOKEN_A))
    assert row.graduated is None, "a revert is not a no"
    assert row.checked_at is None


async def test_the_call_budget_is_counted_not_hidden(session, evm_settings) -> None:
    """Stopping early and finding nothing must not look the same."""
    evm_settings.evm_scan_start_blocks_back = 2_000
    evm_settings.evm_scan_max_blocks_per_run = 2_000
    evm_settings.evm_launchpad_max_calls = 1
    evm = FakeEvm(
        logs=[
            log(TOKEN_A, block=51_999_000),
            log(TOKEN_B, block=51_999_100),
            log(TOKEN_C, block=51_999_200),
        ],
        answers={t: status(False) for t in (TOKEN_A, TOKEN_B, TOKEN_C)},
    )
    provider = EvmLaunchpadProvider(evm_settings, evm=evm)

    result = await scan_launchpad(session, settings=evm_settings, provider=provider)

    assert result.report.status_calls == 1
    assert result.report.unchecked == 2
    unresolved = [
        row for row in await all_launches(session) if row.graduated is None
    ]
    assert len(unresolved) == 2


def select_cursor():
    from sqlalchemy import select

    return select(ChainCursor).where(ChainCursor.name == "launchpad-launches")


def select_launch(address: str):
    from sqlalchemy import select

    return select(LaunchpadLaunch).where(LaunchpadLaunch.address == address)


async def all_launches(session):
    from sqlalchemy import select

    return (await session.scalars(select(LaunchpadLaunch))).all()
