"""The pairing: what a pool is priced in, and whether it changes anything.

A chain that issues tokenised equities has memes quoted against them, and this
system was recording those as if they were quoted in the gas token. A price is
a ratio and the denominator is half of it: a meme quoted in a tokenised share
of a company has a chart that is not separable from that company's, and the
depth on the equity side is a constraint on the meme side.

Four things have to hold for that to be a measurement rather than a story:

- the classification is read off the source, and distinguishes "neither" from
  "nobody said";
- the detector fires on the *appearance* of the pairing and never again, so a
  category does not arrive as one anomaly per token per slot;
- the control token, which never changes denomination, produces nothing;
- rows the source did not describe stay out of *both* arms of the comparison —
  a template that compares two named groups must be able to say a row is
  neither, or silence ends up in the baseline.

No network is touched here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.enums import AnomalyType
from app.providers.market import (
    EQUITY_QUOTE,
    GAS_QUOTE,
    OTHER_QUOTE,
    UNKNOWN_QUOTE,
    _from_pair,
    classify_quote,
)
from app.providers.source import TokenRef
from app.services.observation.detectors import DetectorParams, quote_asset_pairing
from app.services.observation.windows import build_token_window
from app.services.research.templates import TEMPLATES_BY_ANOMALY

BASE = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)
PARAMS = DetectorParams()
REF = TokenRef(
    address="DEMOPAIRxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    symbol="PAIR",
    name="pair",
    decimals=6,
    launch_time=BASE - timedelta(hours=40),
    launchpad="demo-launchpad",
)

MARKER = "• Demo Wrapper"


def window(kinds: list[str | None], liquidity: float = 250_000.0):
    rows = [
        {
            "observed_at": BASE + timedelta(hours=index),
            "liquidity_usd": liquidity,
            "volume_usd": 40_000.0,
            "quote_kind": kind,
            "quote_symbol": "DEMOEQ" if kind == EQUITY_QUOTE else "DEMOGAS",
        }
        for index, kind in enumerate(kinds)
    ]
    return build_token_window(REF, rows)


# -- the classification -----------------------------------------------------


def test_the_marker_is_read_from_the_name(settings) -> None:
    """The name is where the chain writes it; the symbol is free text.

    Anyone can mint a token whose symbol is "NVDA". Classifying on the symbol
    would let that token into the exposed arm for the price of a deploy.
    """
    settings.equity_quote_marker = MARKER
    assert classify_quote("XYZ", f"Acme Corp {MARKER}", settings) == EQUITY_QUOTE
    assert classify_quote("NVDA", "definitely not a wrapper", settings) == OTHER_QUOTE


def test_a_gas_quote_is_the_baseline_arm(settings) -> None:
    settings.gas_quote_symbols = ["ETH", "WETH"]
    assert classify_quote("WETH", "WETH", settings) == GAS_QUOTE
    assert classify_quote("ETH", "Ether", settings) == GAS_QUOTE


def test_silence_is_not_a_kind(settings) -> None:
    """`unknown` and `other` are different answers and must not merge.

    "We asked and it is neither" is evidence. "Nobody told us" is not, and a
    comparison that pools them puts silence in the baseline.
    """
    assert classify_quote(None, None, settings) == UNKNOWN_QUOTE
    assert classify_quote("USDC", "a dollar thing", settings) == OTHER_QUOTE


def test_the_quote_comes_from_the_deepest_pool(settings) -> None:
    """The same pool the price is taken from: the denominator has to belong to
    the numerator."""
    settings.equity_quote_marker = MARKER
    settings.gas_quote_symbols = ["WETH"]
    address = "0x" + "a" * 40
    pairs = [
        {
            "chainId": "demochain",
            "baseToken": {"address": address, "symbol": "MEME", "name": "meme"},
            "quoteToken": {"address": "0x" + "b" * 40, "symbol": "WETH", "name": "WETH"},
            "liquidity": {"usd": 1_000.0},
            "priceUsd": "1",
        },
        {
            "chainId": "demochain",
            "baseToken": {"address": address, "symbol": "MEME", "name": "meme"},
            "quoteToken": {
                "address": "0x" + "c" * 40,
                "symbol": "ACME",
                "name": f"Acme Corp {MARKER}",
            },
            "liquidity": {"usd": 900_000.0},
            "priceUsd": "1",
        },
    ]
    snapshot = _from_pair(address, pairs, "demochain", settings)
    assert snapshot is not None
    assert snapshot.quote_symbol == "ACME"
    assert snapshot.quote_kind == EQUITY_QUOTE
    # Depth still adds up across both pools; only the quote is singular.
    assert snapshot.liquidity_usd == pytest.approx(901_000.0)


# -- the detector -----------------------------------------------------------


def test_the_pairing_fires_when_it_appears() -> None:
    found = quote_asset_pairing(window([GAS_QUOTE] * 4 + [EQUITY_QUOTE]), PARAMS)
    assert found is not None
    assert found.detector == "equity-quote-pairing-v1"
    assert found.anomaly_type == str(AnomalyType.QUOTE_ASSET_PAIRING)
    assert found.score >= 0.1, "a reported anomaly scoring zero reads as a bug"
    assert found.measured["quote_symbol"] == "DEMOEQ"


def test_it_fires_once_and_not_once_per_reading() -> None:
    """The difference between an anomaly and a category.

    Firing on every measurement of an equity-quoted token would bury the
    pipeline under one anomaly per token per slot and report nothing.
    """
    assert quote_asset_pairing(window([GAS_QUOTE, EQUITY_QUOTE, EQUITY_QUOTE]), PARAMS) is None


def test_the_control_stays_silent() -> None:
    assert quote_asset_pairing(window([GAS_QUOTE] * 6), PARAMS) is None


def test_a_null_history_is_not_a_gas_history() -> None:
    """Rows predating the column carry NULL, and NULL is not a kind.

    Reading those as "not an equity" would make every equity-quoted token on
    the chain look like it changed denomination the day the column shipped.
    """
    found = quote_asset_pairing(window([None, None, EQUITY_QUOTE]), PARAMS)
    assert found is not None
    assert found.baseline["prior_kinds_recorded"] == 0


def test_a_pairing_with_no_depth_is_not_reported() -> None:
    """Anyone can open a pool against a tokenised share. Depth is what makes it
    a market, and it is what the score is bound to."""
    assert quote_asset_pairing(window([GAS_QUOTE, EQUITY_QUOTE], liquidity=200.0), PARAMS) is None


def test_the_score_grows_with_depth() -> None:
    shallow = quote_asset_pairing(window([GAS_QUOTE, EQUITY_QUOTE], liquidity=20_000.0), PARAMS)
    deep = quote_asset_pairing(window([GAS_QUOTE, EQUITY_QUOTE], liquidity=400_000.0), PARAMS)
    assert shallow is not None and deep is not None
    assert deep.score > shallow.score


# -- the hypothesis ---------------------------------------------------------


def test_the_template_excludes_what_it_cannot_compare() -> None:
    """`other`, `unknown` and NULL are in neither arm.

    Without this they would all land in the control, and the baseline would be
    "pools quoted in the gas token, plus every pool we could not describe".
    """
    template = TEMPLATES_BY_ANOMALY[str(AnomalyType.QUOTE_ASSET_PAIRING)]
    assert template.eligible({"quote_kind": EQUITY_QUOTE}) is True
    assert template.eligible({"quote_kind": GAS_QUOTE}) is True
    assert template.eligible({"quote_kind": OTHER_QUOTE}) is False
    assert template.eligible({"quote_kind": UNKNOWN_QUOTE}) is False
    assert template.eligible({"quote_kind": None}) is False


def test_the_trigger_and_the_statement_are_the_same_claim() -> None:
    template = TEMPLATES_BY_ANOMALY[str(AnomalyType.QUOTE_ASSET_PAIRING)]
    assert template.trigger(window([GAS_QUOTE, EQUITY_QUOTE]), PARAMS) is True
    assert template.trigger(window([EQUITY_QUOTE, GAS_QUOTE]), PARAMS) is False
    assert template.expected_direction == 1
    assert "tokenised equity" in template.statement
