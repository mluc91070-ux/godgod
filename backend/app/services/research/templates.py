"""Hypothesis templates.

A template turns an anomaly into a *complete* hypothesis: population, sample,
timeframe, baseline, expected result and — the part that makes it a hypothesis
at all — the condition that would falsify it.

Templates are deterministic and parameterised. Model-written hypotheses come
with the external integrations; until then the wording is fixed and the
thinking lives in the trigger, the outcome and the falsification rule.

**Each template owns its scope.** The first version of this file shipped six
templates that were, as questions, two: four of them read the same outcome
(liquidity still at 80%) at the same horizon, against the same baseline, with
the same 5-point threshold. Six near-identical paragraphs is not six lines of
enquiry, and a reader was right to say so. A template now declares its own
trailing window, its own horizon, what it stratifies on, and how large a
difference it is willing to call a result — so that two templates firing on the
same token are genuinely asking different questions of it.

Scope is also constrained by what is actually measured. `holders` and
`holder_concentration_top10` are `None` on every live snapshot, because no
holder indexer is configured; the two templates that depend on them say so in
their population, and will produce an empty comparison rather than a number,
until one is. That is the honest state, not a gap to paper over.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.enums import AnomalyType
from app.services.observation.detectors import DetectorParams
from app.services.observation.windows import TokenWindow, median, ratio

STRATIFICATIONS: dict[str, str] = {
    "liquidity": "chain and liquidity band",
    "age": "chain and token-age band",
    "frame": "chain and sampling frame",
}
"""What a template compares within. The key selects how `DatasetRow.stratum`
is filled; the value is the phrase used wherever a result talks about it.

Every one of them names the chain, because every one of them is held within
one. The population stopped being single-chain when `MARKET_CHAINS` gained a
second entry, and a stratum that did not carry the chain would have started
comparing a bonding-curve memecoin against a token on an execution layer for
tokenised equities, silently, under a label that said "liquidity band"."""


@dataclass(frozen=True)
class HypothesisTemplate:
    """One testable question, and everything needed to test it."""

    key: str
    anomaly_type: str
    question: str
    statement: str
    population: str
    sample_definition: str
    timeframe: str
    baseline: str
    expected_result: str
    falsification_condition: str
    variables: dict[str, Any]

    trigger: Callable[[TokenWindow, DetectorParams], bool]
    """Exposure: did the condition hold at this point in the series?"""

    outcome: Callable[[dict[str, Any], dict[str, Any]], bool | None]
    """Outcome, measured strictly later. None when it cannot be measured."""

    outcome_label: str

    window_hours: float
    """Trailing window the trigger sees, in real hours.

    Measurements land on a quarter-hour grid, so this is not a count of rows —
    it is a span of clock time, and the number of rows inside it varies with
    how long the token has been watched.
    """

    horizon_hours: float
    """How far after exposure the outcome is read, in real hours."""

    expected_direction: int
    """+1 if exposure should raise the outcome rate, -1 if it should lower it.

    Without this a hypothesis is unfalsifiable in practice: an effect in the
    opposite direction to the prediction would otherwise count as confirmation
    as long as it was large enough.
    """

    stratify_by: str = "liquidity"
    """Which comparison the rates are held within. Key of `STRATIFICATIONS`."""

    min_window_points: int = 4
    """Fewest measurements the trailing window may contain and still count.

    A window holding two rows is a window in name only: its median is one of
    the two values, and every deviation from it is half the gap between them.
    """

    min_effect_pp: float = 5.0
    """Below this difference in percentage points the hypothesis is falsified."""

    features: list[str] = field(default_factory=list)

    eligible: Callable[[dict[str, Any]], bool] = lambda row: True
    """Whether a measurement belongs to this question's population at all.

    Default: everything. Most templates compare "the condition held" against
    "the condition did not hold", and every row is one or the other. A template
    that compares two *named* groups needs a third answer — neither — or the
    rows it did not select silently become its baseline. See the pairing
    template, where a pool quoted in something the source never described would
    otherwise be counted as evidence about pools quoted in the gas token.
    """

    @property
    def stratum_label(self) -> str:
        return STRATIFICATIONS[self.stratify_by]


def _volume_spike(window: TokenWindow, params: DetectorParams) -> bool:
    observed = ratio(window.value("volume_usd"), median(window.series("volume_usd")))
    return observed is not None and observed >= params.volume_ratio


def _liquidity_withdrawn(window: TokenWindow, params: DetectorParams) -> bool:
    latest = window.value("liquidity_usd")
    previous = window.previous("liquidity_usd")
    if latest is None or not previous:
        return False
    return (latest - previous) / previous <= -params.liquidity_change_pct


def _concentration_high(window: TokenWindow, params: DetectorParams) -> bool:
    measured = window.value("holder_concentration_top10")
    base = median(window.series("holder_concentration_top10"))
    if measured is None or base is None:
        return False
    return (measured - base) >= params.concentration_jump


def _buy_share_spike(window: TokenWindow, params: DetectorParams) -> bool:
    buys, sells = window.value("buys"), window.value("sells")
    if buys is None or sells is None or (buys + sells) <= 0:
        return False
    share = buys / (buys + sells)
    historical = [
        row["buys"] / (row["buys"] + row["sells"])
        for row in window.history
        if row.get("buys") is not None
        and row.get("sells") is not None
        and (row["buys"] + row["sells"]) > 0
    ]
    base = median(historical)
    return base is not None and (share - base) >= params.buy_share_deviation


def _holder_spike(window: TokenWindow, params: DetectorParams) -> bool:
    deltas = [delta for delta in window.deltas("holders") if delta > 0]
    latest = window.value("holders")
    previous = window.previous("holders")
    if latest is None or previous is None:
        return False
    observed = ratio(latest - previous, median(deltas))
    return observed is not None and observed >= params.holder_growth_ratio


def _equity_quoted(window: TokenWindow, params: DetectorParams) -> bool:
    """Is this measurement's deepest pool priced in a tokenised equity?

    A standing property rather than an event, unlike every other trigger here.
    That is a real difference and it is declared rather than hidden: the critic
    checks independence, and it will see that the exposure of a token's rows is
    perfectly correlated across the series. The alternative — quietly treating
    a structural cohort as if each of its measurements were an independent
    draw — is the thing that check exists to catch.
    """
    from app.providers.market import EQUITY_QUOTE

    return window.latest.get("quote_kind") == EQUITY_QUOTE


def _quoted_in_a_known_asset(row: dict[str, Any]) -> bool:
    """Eligible only if the source described the pair as one of the two arms.

    `other` (a stablecoin, a meme quoted in another meme) and `unknown` (the
    source said nothing) are both excluded, and NULL — a row written before the
    column existed — is excluded with them. None of the three is evidence about
    a gas-quoted pool, and dropping them costs rows where keeping them would
    cost the meaning of the comparison.
    """
    from app.providers.market import EQUITY_QUOTE, GAS_QUOTE

    return row.get("quote_kind") in (EQUITY_QUOTE, GAS_QUOTE)


def _quiet_survivor(window: TokenWindow, params: DetectorParams) -> bool:
    age = window.value("age_seconds")
    liquidity = window.value("liquidity_usd")
    volume = window.value("volume_usd")
    if age is None or liquidity is None or volume is None or liquidity <= 0:
        return False
    return (
        age / 86_400 >= params.survival_age_days
        and liquidity >= params.survival_liquidity_usd
        and volume / liquidity < params.survival_quiet_volume_ratio
    )


# -- outcomes ---------------------------------------------------------------
#
# Six triggers asking about one outcome is one question asked six ways. These
# are the distinct things that can be asked of a live snapshot: does the pool
# keep its depth, does the token stay listed at all, does anyone still trade
# it, does the valuation hold, does the holder base grow.

ALIVE_LIQUIDITY_USD = 1_000.0
"""Below this a pool is not a market. Same floor the launchpad frame uses."""


def _liquidity_held(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    """Did liquidity keep at least 80% of its starting value?"""
    before, after = start.get("liquidity_usd"), later.get("liquidity_usd")
    if before is None or after is None or before <= 0:
        return None
    return after >= 0.8 * before


def _liquidity_survived(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    """Is there still a market at all — not how good a one, whether one."""
    before, after = start.get("liquidity_usd"), later.get("liquidity_usd")
    if before is None or after is None or before < ALIVE_LIQUIDITY_USD:
        return None
    return after >= ALIVE_LIQUIDITY_USD


def _volume_held(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    before, after = start.get("volume_usd"), later.get("volume_usd")
    if before is None or after is None or before <= 0:
        return None
    return after >= 0.5 * before


def _still_trading(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    """Did anyone trade in the hour the later measurement covers?"""
    buys, sells = later.get("buys"), later.get("sells")
    if buys is None or sells is None:
        return None
    return (buys + sells) > 0


def _market_cap_held(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    before, after = start.get("market_cap_usd"), later.get("market_cap_usd")
    if before is None or after is None or before <= 0:
        return None
    return after >= 0.7 * before


def _holders_grew(start: dict[str, Any], later: dict[str, Any]) -> bool | None:
    before, after = start.get("holders"), later.get("holders")
    if before is None or after is None or before <= 0:
        return None
    return after > before * 1.02


TEMPLATES: tuple[HypothesisTemplate, ...] = (
    HypothesisTemplate(
        key="volume-burst-pool-2h",
        anomaly_type=str(AnomalyType.VOLUME_ACCELERATION),
        question="Does a burst of volume mean the pool is still there two hours later?",
        statement=(
            "A measurement where the last hour's volume is at least three times the median "
            "of the preceding three hours is followed, two hours later, by liquidity still "
            "standing at 80% of its level — more often than a measurement in the same "
            "liquidity band with no such burst."
        ),
        population=(
            "Solana tokens under measurement with reported liquidity and hourly volume — "
            "the two fields the market source supplies for every pair"
        ),
        sample_definition=(
            "Measurements holding at least four readings in the preceding three hours and "
            "having a reading two hours later"
        ),
        timeframe="3h of history behind each measurement; the outcome read 2h after it",
        baseline="Measurements in the same liquidity band where volume did not spike",
        expected_result=(
            "Bursts are followed by intact liquidity more often than quiet measurements are"
        ),
        falsification_condition=(
            "The gap is under 8 percentage points, points the other way, or does not survive "
            "being split by liquidity band"
        ),
        variables={
            "independent": ["volume_over_median"],
            "dependent": ["liquidity_retained"],
            "controls": ["chain", "liquidity_stratum"],
        },
        trigger=_volume_spike,
        outcome=_liquidity_held,
        outcome_label="liquidity still at 80% of its level",
        window_hours=3,
        horizon_hours=2,
        expected_direction=1,
        stratify_by="liquidity",
        min_effect_pp=8.0,
        features=["volume_usd", "liquidity_usd", "age_seconds"],
    ),
    HypothesisTemplate(
        key="withdrawal-death-12h",
        anomaly_type=str(AnomalyType.LIQUIDITY_CHANGE),
        question="Is a token that loses a third of its pool dead half a day later?",
        statement=(
            "A measurement in which liquidity fell by at least 35% against the reading "
            "before it is followed, twelve hours later, by a pool still worth $1,000 less "
            "often than a measurement in the same liquidity band with no such fall."
        ),
        population=(
            "Solana tokens whose pool was worth at least $1,000 at the moment of exposure — "
            "below that there is no market left to lose"
        ),
        sample_definition=(
            "Measurements with a reading in the preceding hour to compare against, and a "
            "reading twelve hours later"
        ),
        timeframe="one step back for the fall; the outcome read 12h after it",
        baseline="Measurements in the same liquidity band with no withdrawal",
        expected_result="Withdrawals are followed by dead pools far more often",
        falsification_condition=(
            "Survival after a withdrawal is not at least 20 percentage points rarer than "
            "the baseline — a smaller gap would not distinguish a withdrawal from ordinary "
            "attrition — or the direction flips between liquidity bands"
        ),
        variables={
            "independent": ["liquidity_change_pct"],
            "dependent": ["pool_still_alive"],
            "controls": ["chain", "liquidity_stratum"],
        },
        trigger=_liquidity_withdrawn,
        outcome=_liquidity_survived,
        outcome_label="pool still worth $1,000",
        window_hours=1,
        horizon_hours=12,
        expected_direction=-1,
        stratify_by="liquidity",
        min_window_points=2,
        min_effect_pp=20.0,
        features=["liquidity_usd", "volume_usd"],
    ),
    HypothesisTemplate(
        key="buy-surge-trading-1h",
        anomaly_type=str(AnomalyType.UNUSUAL_TRANSACTION_PATTERN),
        question="When buying goes one-sided, is anyone still trading an hour later?",
        statement=(
            "A measurement where buys make up at least 10 points more of the trade count "
            "than the median of the preceding six hours is followed, one hour later, by at "
            "least one trade more often than a measurement on a token of the same age with "
            "no such shift."
        ),
        population=(
            "Solana tokens with reported buy and sell counts, at every age from minutes "
            "old to months old"
        ),
        sample_definition=(
            "Measurements holding at least four readings in the preceding six hours and "
            "having a reading one hour later"
        ),
        timeframe="6h of history behind each measurement; the outcome read 1h after it",
        baseline=(
            "Measurements on tokens in the same age band — new, young, established, old — "
            "with no buy-side shift"
        ),
        expected_result="One-sided buying is followed by continued trading more often",
        falsification_condition=(
            "The gap is under 6 percentage points, points the other way, or reverses "
            "between age bands"
        ),
        variables={
            "independent": ["buy_share_deviation"],
            "dependent": ["still_trading"],
            "controls": ["chain", "age_stratum"],
        },
        trigger=_buy_share_spike,
        outcome=_still_trading,
        outcome_label="at least one trade in the following hour",
        window_hours=6,
        horizon_hours=1,
        expected_direction=1,
        stratify_by="age",
        min_effect_pp=6.0,
        features=["buys", "sells", "transactions", "age_seconds"],
    ),
    HypothesisTemplate(
        key="quiet-survivor-frame-12h",
        anomaly_type=str(AnomalyType.TOKEN_SURVIVAL_ANOMALY),
        question="Do the old quiet ones hold their depth better over half a day?",
        statement=(
            "A measurement on a token older than seven days, holding at least $10,000 of "
            "liquidity and trading under a quarter of it per hour, is followed twelve hours "
            "later by liquidity still at 80% of its level more often than a measurement "
            "found through the same feed on a token that is not quiet."
        ),
        population=(
            "Solana tokens with a recorded age and liquidity, split by which feed found "
            "them: a paid promotion or a completed bonding curve"
        ),
        sample_definition=(
            "Measurements holding at least four readings in the preceding six hours and "
            "having a reading twelve hours later"
        ),
        timeframe="6h of history behind each measurement; the outcome read 12h after it",
        baseline=(
            "Measurements from the same sampling frame — promotion feed or launchpad "
            "migration — on tokens that are not quiet survivors"
        ),
        expected_result="Quiet survivors hold their depth more often, in either frame",
        falsification_condition=(
            "The gap is under 10 percentage points, points the other way, or holds in one "
            "sampling frame and reverses in the other — which would make it a fact about "
            "how the token was found, not about the token"
        ),
        variables={
            "independent": ["age_days", "volume_over_liquidity"],
            "dependent": ["liquidity_retained"],
            "controls": ["chain", "sampling_frame"],
        },
        trigger=_quiet_survivor,
        outcome=_liquidity_held,
        outcome_label="liquidity still at 80% of its level",
        window_hours=6,
        horizon_hours=12,
        expected_direction=1,
        stratify_by="frame",
        min_effect_pp=10.0,
        features=["age_seconds", "liquidity_usd", "volume_usd"],
    ),
    HypothesisTemplate(
        key="concentration-valuation-6h",
        anomaly_type=str(AnomalyType.WALLET_CONCENTRATION_CHANGE),
        question="Does the top of the holder table tightening precede the valuation falling?",
        statement=(
            "A measurement where the top ten wallets' share rises at least 15 points above "
            "its six-hour median is followed six hours later by a market cap still at 70% "
            "of its level less often than a measurement in the same liquidity band with no "
            "such tightening."
        ),
        population=(
            "Solana tokens with a measured holder distribution. No holder indexer is "
            "configured, so this field is currently null on every snapshot and this "
            "comparison has no rows — it is stated, not answered"
        ),
        sample_definition=(
            "Measurements holding at least four readings of the top-ten share in the "
            "preceding six hours and a market cap six hours later"
        ),
        timeframe="6h of history behind each measurement; the outcome read 6h after it",
        baseline="Measurements in the same liquidity band with a flat holder table",
        expected_result="Tightening is followed by a fallen valuation more often",
        falsification_condition=(
            "The gap is under 12 percentage points, points the other way, or reverses "
            "between liquidity bands"
        ),
        variables={
            "independent": ["concentration_jump"],
            "dependent": ["market_cap_retained"],
            "controls": ["chain", "liquidity_stratum"],
        },
        trigger=_concentration_high,
        outcome=_market_cap_held,
        outcome_label="market cap still at 70% of its level",
        window_hours=6,
        horizon_hours=6,
        expected_direction=-1,
        stratify_by="liquidity",
        min_effect_pp=12.0,
        features=["holder_concentration_top10", "market_cap_usd", "liquidity_usd"],
    ),
    HypothesisTemplate(
        key="holder-rush-momentum",
        anomaly_type=str(AnomalyType.HOLDER_ACCELERATION),
        question="Once new holders start arriving fast, do they keep arriving?",
        statement=(
            "A measurement where the holder count grew at least three times faster than "
            "its usual step is followed six hours later by a holder base at least 2% "
            "larger more often than a measurement on a token of the same age growing at "
            "its ordinary rate."
        ),
        population=(
            "Solana tokens with a measured holder count. No holder indexer is configured, "
            "so this field is null on every snapshot and this comparison has no rows — the "
            "question is on the record, unanswered"
        ),
        sample_definition=(
            "Measurements holding at least four readings in the preceding six hours and a "
            "holder count six hours later"
        ),
        timeframe="6h of history behind each measurement; the outcome read 6h after it",
        baseline=(
            "Measurements on tokens in the same age band whose holder count grew at its "
            "ordinary rate"
        ),
        expected_result=(
            "A rush is followed by continued growth more often — a holder base is a "
            "cumulative count, so arrivals are expected to cluster rather than reverse"
        ),
        falsification_condition=(
            "The gap is under 8 percentage points, points the other way — which would make "
            "a rush a top rather than a beginning — or reverses between age bands"
        ),
        variables={
            "independent": ["holder_growth_ratio"],
            "dependent": ["holders_grew"],
            "controls": ["chain", "age_stratum"],
        },
        trigger=_holder_spike,
        outcome=_holders_grew,
        outcome_label="holder base at least 2% larger",
        window_hours=6,
        horizon_hours=6,
        expected_direction=1,
        stratify_by="age",
        min_effect_pp=8.0,
        features=["holders", "liquidity_usd", "volume_usd"],
    ),
    HypothesisTemplate(
        key="equity-quoted-market-cap-6h",
        anomaly_type=str(AnomalyType.QUOTE_ASSET_PAIRING),
        question=(
            "Does pricing a meme in a tokenised share hold its valuation better than "
            "pricing it in the gas token?"
        ),
        statement=(
            "A measurement of a token whose deepest pool is quoted in a tokenised equity "
            "is followed, six hours later, by a market cap still standing at 70% of its "
            "level — more often than a measurement of a token in the same chain and "
            "liquidity band whose deepest pool is quoted in the chain's own gas token."
        ),
        population=(
            "Tokens on a chain that issues tokenised equities, measured with a quote "
            "asset the source described — either an equity wrapper or the gas token. A "
            "pool quoted in anything else, or in something the source did not name, is "
            "in neither arm"
        ),
        sample_definition=(
            "Measurements holding at least four readings in the preceding six hours, a "
            "recorded quote asset, and a reading six hours later"
        ),
        timeframe="6h of history behind each measurement; the outcome read 6h after it",
        baseline=(
            "Measurements in the same chain and liquidity band whose deepest pool is "
            "quoted in the gas token"
        ),
        expected_result=(
            "Equity-quoted tokens hold their valuation more often, because the "
            "denominator is an asset with an off-chain price and a redemption path "
            "rather than one that falls with the same risk appetite the meme rises on"
        ),
        falsification_condition=(
            "The gap is under 6 percentage points, points the other way — which would "
            "mean the equity denominator transmits its own drawdowns rather than "
            "damping the meme's — or reverses between liquidity bands"
        ),
        variables={
            "independent": ["quote_kind"],
            "dependent": ["market_cap_held"],
            "controls": ["chain", "liquidity_stratum"],
        },
        trigger=_equity_quoted,
        outcome=_market_cap_held,
        outcome_label="market cap at least 70% of its level",
        window_hours=6,
        horizon_hours=6,
        expected_direction=1,
        stratify_by="liquidity",
        min_effect_pp=6.0,
        features=["quote_kind", "market_cap_usd", "liquidity_usd"],
        eligible=_quoted_in_a_known_asset,
    ),
)

# SOCIAL_ONCHAIN_DIVERGENCE deliberately has no template. Its exposure — talk
# rising while participation stays flat — needs a mentions series alongside the
# snapshot series, and mentions are not stored per snapshot, so a dataset built
# from `token_snapshots` cannot reproduce it. The previous version of this file
# papered over that by giving the divergence template a holder-acceleration
# trigger, so a published statement about attention was tested by a rule about
# holder counts. The trigger has gone where it belongs and the question waits
# for the data it actually needs.

TEMPLATES_BY_ANOMALY: dict[str, HypothesisTemplate] = {
    template.anomaly_type: template for template in TEMPLATES
}
TEMPLATES_BY_KEY: dict[str, HypothesisTemplate] = {
    template.key: template for template in TEMPLATES
}
