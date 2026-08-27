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

Two populations are sampled, and every token records which one found it:

- **promoted** — the promotion feed. Somebody paid to put it there.
- **migrated** — a bonding curve that filled. Nobody paid for placement; the
  crowd bought it one trade at a time.

They are kept apart because they are not the same population, and a result that
holds in one and not the other is a result about the sampling frame. Both are
measured by the same market provider into identical rows, so they stay
comparable.

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
SNAPSHOT_SOURCE = "live-market-v2"
"""v2 stores one-hour volume and trade counts instead of twenty-four hour
ones. Rows from v1 are not comparable with these and keep their own tag."""


@dataclass
class ChainReport:
    candidates: int = 0
    measured: int = 0
    tokens_created: int = 0
    snapshots_stored: int = 0
    distributions_measured: int = 0
    """Tokens whose top-10 share the RPC could actually compute."""
    migrations_seen: int = 0
    """Completed bonding curves the launchpad reported this run."""
    migrations_measured: int = 0
    """Of those, the ones the market API could actually measure."""
    launchpad_error: str | None = None
    """Named apart from `error`: the promotion feed can work while the
    launchpad is down, and a run that lost one frame is not a failed run."""
    dropped: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "measured": self.measured,
            "tokens_created": self.tokens_created,
            "snapshots_stored": self.snapshots_stored,
            "distributions_measured": self.distributions_measured,
            "migrations_seen": self.migrations_seen,
            "migrations_measured": self.migrations_measured,
            "launchpad_error": self.launchpad_error,
            "dropped": self.dropped,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "complete": self.error is None and self.launchpad_error is None,
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
    token = await session.scalar(select(Token).where(Token.address == snapshot.address))
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
    # Snapshots are keyed to the quarter hour. Meme markets move in minutes,
    # so hourly sampling both loses the shape of a move and makes the system
    # take six hours to say anything at all.
    now = datetime.now(UTC)
    observed_at = as_utc(as_of) or now.replace(
        minute=(now.minute // 15) * 15, second=0, microsecond=0
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

    # De-duplicate across queries, keeping the deepest measurement of each token.
    unique: dict[str, MarketSnapshot] = {}
    for snapshot in candidates:
        existing = unique.get(snapshot.address)
        if existing is None or (snapshot.liquidity_usd or 0) > (existing.liquidity_usd or 0):
            unique[snapshot.address] = snapshot
    report.candidates = len(unique)

    budget = settings.chain_max_tokens + (settings.launchpad_max_tokens if migrations else 0)
    for snapshot in list(unique.values())[:budget]:
        migration = migrations.get(snapshot.address)
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

        if snapshot.liquidity_usd is None:
            report.drop("liquidity_not_reported")
            continue
        if snapshot.liquidity_usd < min_liquidity:
            report.drop(f"below_liquidity_floor_{frame}")
            continue
        # The floor asks "is this token traded at all", which is a question about
        # the token rather than about this hour, so it uses the 24h figure.
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
                is_demo=False,
                **fields,
            )
        )
        await session.flush()
        report.measured += 1
        report.snapshots_stored += 1

    report.duration_ms = int((utcnow() - started).total_seconds() * 1000)

    message = (
        f"chain collector: {report.snapshots_stored} measurements of "
        f"{report.candidates} candidates"
    )
    if report.migrations_seen:
        message += f", {report.migrations_seen} freshly migrated"
    if report.distributions_measured:
        message += f", {report.distributions_measured} with a holder distribution"
    if report.error:
        message += f" — {report.error}"
    if report.launchpad_error:
        message += f" — launchpad: {report.launchpad_error}"

    session.add(
        SystemEvent(
            seq=await _next_event_seq(session),
            event_type=str(EventType.ERROR if report.error else EventType.OBSERVATION),
            message=message,
            level="WARN" if (report.error or report.launchpad_error) else "INFO",
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
