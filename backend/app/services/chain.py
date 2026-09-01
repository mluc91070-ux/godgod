"""Measuring real tokens.

One pass: find candidates, measure each, store one `token_snapshots` row per
token. The observation pipeline then reads those rows exactly as it reads the
synthetic ones — that is the whole reason the source interface exists, and why
nothing in the pipeline changes when this module starts running.

Three things this module refuses to do:

- **Invent a holder count.** A public RPC node cannot supply one; it needs an
  indexer. `holders` stays `NULL`, and the detectors that need it return no
  verdict rather than a wrong one.
- **Report a partial run as a complete one.** A rate-limited node or an
  unreachable market API produces `complete: false` with the reason.
- **Mix live rows with fixtures.** Everything written here is `is_demo=False`.

- **Measure one chain with another chain's node.** The RPC client speaks
  Solana. It is asked for a holder distribution only on Solana rows; anywhere
  else the share stays `NULL` under a named drop, because "the endpoint that
  could answer this was never called" is not the same as "there is no answer".

Two populations are sampled on every configured chain, and every token records
which frame found it and which network it lives on:

- **promoted** — the promotion feed. Somebody paid to put it there.
- **migrated** — a bonding curve that filled. Nobody paid for placement; the
  crowd bought it one trade at a time.

On top of the two frames there is a third *selection rule*, which is a
different kind of thing and is recorded in a different column. A token above
`CHAIN_RETAIN_MIN_MARKET_CAP_USD` is re-measured every run whether or not the
feed still names it, and `TokenSnapshot.selected_by` records why each row
exists. The frame says how a token was found and is written once; the rule says
why this measurement was taken and can differ between two rows of the same
token.

Retention exists because the alternative was measured: 12,284 readings across
3,732 tokens is a mean of 3.3 each against a threshold of 6, so most tokens
left the feed before a detector was ever allowed to speak about them. A
retained token reaches the threshold in six consecutive quarter hours and then
keeps going, and it keeps being measured after it falls through the floors —
a large cap that drains is the outcome the exposure was interesting for, and
dropping it there would be survivorship bias built into the collector.

They are kept apart because they are not the same population, and a result that
holds in one and not the other is a result about the sampling frame. Both are
measured by the same market provider into identical rows, so they stay
comparable.

The chain is the second such axis, and it is kept apart for the same reason.
The promotion feed is not single-chain; `MARKET_CHAINS` names the networks
read, `Token.chain` records the one each row came from, and every comparison is
held within one chain rather than pooled across two — a bonding-curve memecoin
and a token on an execution layer built for tokenised equities are not one
population, and averaging them would answer a question nobody asked.

The migration frame is Solana-only, and not by omission: it is read from a
launchpad that reports completed bonding curves, and that launchpad covers one
chain. A token on any other chain therefore enters through the promotion frame
or not at all, which is a limit of the source and is recorded as one.

It also cannot fabricate history. The first run of this collector produces one
measurement per token, and the pipeline needs `OBSERVATION_MIN_SNAPSHOTS` of
them before any detector will speak. That silence is correct: a system that has
watched a token for one hour has not seen a trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import EventType
from app.models import AgentRun, SystemEvent, Token, TokenSnapshot
from app.models.base import as_utc, utcnow
from app.providers.base import ProviderNotConfigured
from app.providers.launchpad import (
    LaunchpadCallFailed,
    LaunchpadProvider,
    MigratedToken,
    get_launchpad_provider,
)
from app.providers.market import (
    MarketCallFailed,
    MarketProvider,
    MarketSnapshot,
    get_market_provider,
)
from app.providers.solana import RpcCallFailed, get_solana_provider

CHAIN_RUN_NAME = "chain-collector"
SNAPSHOT_SOURCE = "live-market-v3"
"""v2 stored one-hour volume and trade counts instead of twenty-four hour
ones. v3 changes no field: it marks where the *sampling* changed — a ten-minute
slot instead of fifteen, and entry floors raised to $50k liquidity and $100k
daily volume. The rows are the same shape; the population they were drawn from
is not, and a series that crosses the seam should be able to say where it is.
Rows from earlier versions keep their own tag."""


@dataclass
class ChainReport:
    candidates: int = 0
    measured: int = 0
    tokens_created: int = 0
    snapshots_stored: int = 0
    distributions_measured: int = 0
    """Tokens whose top-10 share the RPC could actually compute."""
    retained: int = 0
    """Measurements taken because the token is above the retention floor,
    rather than because the feed named it this run."""
    by_chain: dict[str, int] = field(default_factory=dict)
    """Measurements stored per chain. A run that reached one chain and not the
    other is not a smaller run, it is a run with a hole in it."""
    migrations_seen: int = 0
    """Completed bonding curves the launchpad reported this run."""
    migrations_measured: int = 0
    """Of those, the ones the market API could actually measure."""
    launchpad_error: str | None = None
    """Named apart from `error`: the promotion feed can work while the
    launchpad is down, and a run that lost one frame is not a failed run."""
    retention_error: str | None = None
    """Same reasoning for the retained cohort: losing it costs those readings,
    not the discovery run that already succeeded."""
    dropped: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def count_chain(self, chain: str) -> None:
        self.by_chain[chain] = self.by_chain.get(chain, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "measured": self.measured,
            "tokens_created": self.tokens_created,
            "snapshots_stored": self.snapshots_stored,
            "by_chain": self.by_chain,
            "retained": self.retained,
            "distributions_measured": self.distributions_measured,
            "migrations_seen": self.migrations_seen,
            "migrations_measured": self.migrations_measured,
            "launchpad_error": self.launchpad_error,
            "retention_error": self.retention_error,
            "dropped": self.dropped,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "complete": (
                self.error is None
                and self.launchpad_error is None
                and self.retention_error is None
            ),
            "llm_calls": 0,
        }


PROMOTED = "promotion-feed"
MIGRATED = "launchpad-migration"
"""The two sampling frames. Stored on `Token.source` so every experiment can
say which population it drew from instead of implying a neutral one."""


def _apply_migration(token: Token, migration: MigratedToken) -> None:
    """Record what the launchpad said, and only what it said.

    `bonding_curve_state` is set to "complete" because the source reported the
    curve complete. `migrated_to_dex` holds the destination pool the payload
    named — absent means the field stays NULL rather than naming a venue
    nobody confirmed.
    """
    token.launchpad = token.launchpad or "bonding-curve"
    token.bonding_curve_state = "complete"
    if migration.pool and not token.migrated_to_dex:
        token.migrated_to_dex = migration.pool
    if migration.created_at and token.launch_time is None:
        token.launch_time = migration.created_at


async def _get_or_create_token(
    session: AsyncSession,
    snapshot: MarketSnapshot,
    report: ChainReport,
    *,
    migration: MigratedToken | None = None,
) -> Token:
    # Keyed on the pair, not on the address. An address is only a token
    # together with its network: the same string is a different asset on a
    # different chain, and looking it up by address alone would attach one
    # chain's measurement to another chain's row.
    token = await session.scalar(
        select(Token).where(
            Token.address == snapshot.address, Token.chain == snapshot.chain
        )
    )
    if token is not None:
        if snapshot.symbol and not token.symbol:
            token.symbol = snapshot.symbol
        if snapshot.name and not token.name:
            token.name = snapshot.name
        if migration is not None:
            _apply_migration(token, migration)
        return token

    token = Token(
        address=snapshot.address,
        # The network the measurement was taken on, as the market source
        # reported it — never defaulted to Solana because that is what this
        # collector used to read.
        chain=snapshot.chain,
        symbol=snapshot.symbol,
        name=snapshot.name,
        launch_time=snapshot.created_at,
        # The frame that found it first. Never overwritten later: a token that
        # was promoted and then migrated entered this dataset as promoted, and
        # rewriting that would change the population of every past experiment.
        source=MIGRATED if migration is not None else PROMOTED,
        is_demo=False,
    )
    if migration is not None:
        _apply_migration(token, migration)
    session.add(token)
    await session.flush()
    report.tokens_created += 1
    return token


async def _already_measured(
    session: AsyncSession, token_id: str, observed_at: datetime
) -> bool:
    """One row per token per measurement time.

    SQLite hands back naive datetimes, so both sides are normalised before they
    are compared — the same trap that once turned 144 snapshots into 756.
    """
    rows = (
        await session.scalars(
            select(TokenSnapshot.observed_at).where(TokenSnapshot.token_id == token_id)
        )
    ).all()
    target = as_utc(observed_at)
    return any(as_utc(row) == target for row in rows)


async def _retained_addresses(
    session: AsyncSession, settings: Settings
) -> dict[str, list[str]]:
    """The tokens big enough to keep measuring, per chain.

    Read from the most recent *snapshot*, never from `Token.market_cap_usd`:
    that column is a cached latest value with no timestamp attached, and a
    selection rule has to be reconstructible from a measurement that says when
    it was taken.

    Per chain and not in total, because in total the largest caps on one
    network would fill every slot and the other would never be retained at all
    — a budget rule quietly deciding which population gets studied.

    Ordered by market cap descending, so the rule is deterministic: the same
    database produces the same cohort, and nothing here breaks a tie at random.
    """
    if settings.chain_retain_max_tokens <= 0:
        return {}

    latest = (
        select(
            TokenSnapshot.token_id.label("token_id"),
            func.max(TokenSnapshot.observed_at).label("observed_at"),
        )
        .group_by(TokenSnapshot.token_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Token.chain, Token.address, TokenSnapshot.market_cap_usd)
            .join(latest, latest.c.token_id == Token.id)
            .join(
                TokenSnapshot,
                (TokenSnapshot.token_id == Token.id)
                & (TokenSnapshot.observed_at == latest.c.observed_at),
            )
            .where(
                Token.is_demo.is_(False),
                Token.chain.in_(settings.market_chains),
                TokenSnapshot.market_cap_usd.is_not(None),
                TokenSnapshot.market_cap_usd >= settings.chain_retain_min_market_cap_usd,
            )
            .order_by(TokenSnapshot.market_cap_usd.desc())
        )
    ).all()

    by_chain: dict[str, list[str]] = {}
    for chain, address, _cap in rows:
        held = by_chain.setdefault(chain, [])
        if len(held) < settings.chain_retain_max_tokens and address not in held:
            held.append(address)
    return by_chain


async def _next_event_seq(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.max(SystemEvent.seq))) or 0) + 1


async def collect_chain(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    market: MarketProvider | None = None,
    chain: Any = None,
    launchpad: LaunchpadProvider | None = None,
    as_of: datetime | None = None,
    commit: bool = True,
) -> ChainReport:
    """Measure the tokens worth measuring, once."""
    settings = settings or get_settings()
    market = market or get_market_provider(settings)
    chain = chain or get_solana_provider(settings)
    launchpad = launchpad or get_launchpad_provider(settings)
    started = utcnow()
    # Snapshots are keyed to a slot on the clock, not to the moment the run
    # started. Meme markets move in minutes, so hourly sampling both loses the
    # shape of a move and makes the system take six hours to say anything.
    #
    # The slot is derived from the collection interval rather than fixed, so
    # the two cannot drift apart: a loop faster than the slot spends requests
    # landing where a measurement already exists.
    now = datetime.now(UTC)
    slot = settings.snapshot_slot_minutes
    observed_at = as_utc(as_of) or now.replace(
        minute=(now.minute // slot) * slot, second=0, microsecond=0
    )
    report = ChainReport()

    candidates: list[MarketSnapshot] = []
    try:
        if settings.chain_discover:
            candidates.extend(await market.discover(limit=settings.chain_max_tokens))
        else:
            for query in settings.chain_watch_queries:
                candidates.extend(
                    await market.search(query, limit=settings.chain_max_tokens)
                )
    except (ProviderNotConfigured, MarketCallFailed) as exc:
        report.error = f"{type(exc).__name__}: {exc}"

    # The second frame. Migrations are read from the launchpad and measured by
    # the market provider, so a migrated token produces the same row shape as a
    # promoted one. A launchpad failure costs this cohort, not the run.
    migrations: dict[str, MigratedToken] = {}
    if not settings.launchpad_migrations:
        pass
    elif not launchpad.implemented:
        # Not configured is a decision, not a failure — but it is recorded, so
        # that a run with no migrations is distinguishable from a run that
        # never looked for any.
        report.drop("launchpad_not_configured")
    else:
        try:
            reported = await launchpad.recent_migrations(
                limit=settings.launchpad_max_tokens
            )
            report.migrations_seen = len(reported)
            migrations = {item.address: item for item in reported}
            if migrations:
                measured = await market.snapshots(list(migrations))
                report.migrations_measured = len(measured)
                # Absent from the market means no pair exists yet. That is a
                # real state of a just-migrated token, and it is counted, not
                # filled in with zeros.
                for address in migrations:
                    if not any(item.address == address for item in measured):
                        report.drop("migration_not_yet_on_market")
                candidates.extend(measured)
        except (ProviderNotConfigured, LaunchpadCallFailed, MarketCallFailed) as exc:
            report.launchpad_error = f"{type(exc).__name__}: {exc}"

    # The third rule. A token above the retention floor is measured every run,
    # whether or not the feed still names it, because a series with holes in it
    # is not a shorter series — it is a different one, and most tokens here
    # rotate out of the promotion feed before any detector is allowed to speak.
    #
    # A retained token is measured even when it has fallen through the floors a
    # discovered one must clear. That is the point: a token that held a large
    # market cap and then drained is the most informative row in the dataset,
    # and the discovery floors would drop it exactly when it became
    # interesting. Every such row records `selected_by="retention"` so the two
    # rules never sit in one column unlabelled.
    retained: set[tuple[str, str]] = set()
    try:
        for chain_id, addresses in (await _retained_addresses(session, settings)).items():
            measured = await market.snapshots(addresses, chain_id)
            for address in addresses:
                if not any(item.address == address for item in measured):
                    # No pair right now. A real state of a drained token, and
                    # counted rather than filled in with zeroes.
                    report.drop("retained_not_on_market")
            for item in measured:
                retained.add((item.chain, item.address))
            candidates.extend(measured)
    except (ProviderNotConfigured, MarketCallFailed) as exc:
        # Named apart from `error`: losing the retained cohort costs this
        # cohort's readings, not the discovery run that already succeeded.
        report.drop("retention_measurement_failed")
        report.retention_error = f"{type(exc).__name__}: {exc}"

    # De-duplicate, keeping the deepest measurement of each token. Keyed on the
    # chain *and* the address: the same string is a different token on a
    # different network, and one key would fold two of them together.
    unique: dict[tuple[str, str], MarketSnapshot] = {}
    for snapshot in candidates:
        key = (snapshot.chain, snapshot.address)
        existing = unique.get(key)
        if existing is None or (snapshot.liquidity_usd or 0) > (existing.liquidity_usd or 0):
            unique[key] = snapshot
    report.candidates = len(unique)

    budget = (
        settings.chain_max_tokens
        + (settings.launchpad_max_tokens if migrations else 0)
        + len(retained)
    )
    for snapshot in list(unique.values())[:budget]:
        # Migrations are read from a launchpad that covers one chain, so the
        # lookup is only meaningful there. Without the guard an address that
        # collided across networks would inherit the other chain's curve.
        migration = (
            migrations.get(snapshot.address) if snapshot.chain == "solana" else None
        )
        keep = (snapshot.chain, snapshot.address) in retained
        # The floors are per-frame because they answer different questions. On
        # the promotion feed the risk is a deep pool nobody trades — a parked
        # balance. A token that migrated twenty minutes ago cannot be one, and
        # the promotion floor rejects it for the opposite reason: too thin. See
        # `launchpad_min_liquidity_usd` for the run that measured this.
        min_liquidity = (
            settings.launchpad_min_liquidity_usd
            if migration is not None
            else settings.chain_min_liquidity_usd
        )
        min_volume = (
            settings.launchpad_min_volume_usd
            if migration is not None
            else settings.chain_min_volume_usd
        )
        frame = "migration" if migration is not None else "promotion"
        selected_by = (
            "retention" if keep else "migration" if migration is not None else "discovery"
        )

        # The floors decide what is worth *entering* the dataset. A retained
        # token is already in it, and the question about it is what happens
        # next — including the pool draining, which is what the floors reject.
        # Applying them here would delete the outcome and keep the exposure.
        if not keep:
            if snapshot.liquidity_usd is None:
                report.drop("liquidity_not_reported")
                continue
            if snapshot.liquidity_usd < min_liquidity:
                report.drop(f"below_liquidity_floor_{frame}")
                continue
            # The floor asks "is this token traded at all", which is a question
            # about the token rather than about this hour, so it uses the 24h
            # figure.
            if snapshot.volume_24h_usd is None:
                report.drop("volume_not_reported")
                continue
            if snapshot.volume_24h_usd < min_volume:
                # A deep pool nobody trades in is a parked balance, not a market.
                report.drop(f"below_volume_floor_{frame}")
                continue

        token = await _get_or_create_token(
            session, snapshot, report, migration=migration
        )
        if await _already_measured(session, token.id, observed_at):
            report.drop("already_measured_this_slot")
            continue

        # The RPC is asked only for what the market data cannot supply. A
        # failure here costs the distribution, not the whole measurement.
        top10_share = None
        if snapshot.chain != "solana":
            # And it is asked only where it can answer. The client speaks
            # Solana; an address on another chain is not a mint it can look
            # up, so the call is not made and the share stays NULL under its
            # own reason. Calling anyway and recording the error would file a
            # design decision as a fault, and the two need different fixes.
            report.drop("holder_distribution_chain_unsupported")
        else:
            try:
                distribution = await chain.get_holder_distribution(snapshot.address)
                top10_share = distribution.top10_share
                if distribution.measurable:
                    report.distributions_measured += 1
                else:
                    report.drop("holder_distribution_not_reported")
            except RpcCallFailed as exc:
                # Named separately because the fix differs: a throttled endpoint
                # needs a dedicated RPC url, an unconfigured one needs any url.
                report.drop(
                    "holder_distribution_rate_limited"
                    if "rate-limited" in str(exc)
                    else "holder_distribution_failed"
                )
            except (ProviderNotConfigured, AttributeError):
                report.drop("holder_distribution_unavailable")

        fields = snapshot.as_snapshot_fields()
        session.add(
            TokenSnapshot(
                token_id=token.id,
                observed_at=observed_at,
                holders=None,  # No indexer, no holder count. Never a guess.
                holder_concentration_top10=top10_share,
                source=SNAPSHOT_SOURCE,
                selected_by=selected_by,
                is_demo=False,
                **fields,
            )
        )
        await session.flush()
        report.measured += 1
        report.snapshots_stored += 1
        report.count_chain(token.chain)
        if keep:
            report.retained += 1

    report.duration_ms = int((utcnow() - started).total_seconds() * 1000)

    message = (
        f"chain collector: {report.snapshots_stored} measurements of "
        f"{report.candidates} candidates"
    )
    if report.by_chain:
        message += " on " + ", ".join(
            f"{count} {chain}" for chain, count in sorted(report.by_chain.items())
        )
    if report.retained:
        message += f", {report.retained} retained above the market-cap floor"
    if report.migrations_seen:
        message += f", {report.migrations_seen} freshly migrated"
    if report.distributions_measured:
        message += f", {report.distributions_measured} with a holder distribution"
    if report.error:
        message += f" — {report.error}"
    if report.launchpad_error:
        message += f" — launchpad: {report.launchpad_error}"
    if report.retention_error:
        message += f" — retention: {report.retention_error}"

    session.add(
        SystemEvent(
            seq=await _next_event_seq(session),
            event_type=str(EventType.ERROR if report.error else EventType.OBSERVATION),
            message=message,
            level=(
                "WARN"
                if (report.error or report.launchpad_error or report.retention_error)
                else "INFO"
            ),
            ref_type="chain-collector",
            occurred_at=datetime.now(UTC),
            is_demo=False,
        )
    )
    session.add(
        AgentRun(
            agent_name=CHAIN_RUN_NAME,
            model=None,
            input_summary=(
            "discovery: promotion feed"
            if settings.chain_discover
            else f"queries: {', '.join(settings.chain_watch_queries)[:400]}"
        ),
            output_summary=message[:2000],
            duration_ms=report.duration_ms,
            status="ERROR" if report.error else "OK",
            error=report.error,
            estimated_cost_usd=0.0,
            started_at=started,
            is_demo=False,
        )
    )
    await session.flush()

    if commit:
        await session.commit()
    return report
