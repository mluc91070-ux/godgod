"""Finding completed bonding curves on a chain, incrementally.

The API-backed launchpad answers "what migrated recently" in one call. A chain
cannot, and the reason is worth writing down because it shapes everything here:

- launches are log entries, and this node refuses a range wider than two
  thousand blocks — about eight minutes of chain;
- graduation is contract state that flips hours or days after the launch, and
  is readable only one token at a time.

No window holds both. So the launch is written down when it is seen, a cursor
records how far the logs have been read, and the unresolved launches are
re-asked on later runs until they finish or the recheck window closes.

What this refuses to do:

- **Turn silence into a negative.** `graduated` is three-valued. NULL means
  nobody managed to ask — a rate-limited node, a contract that reverted, a run
  that hit its call budget — and it is never rendered as "did not migrate".
- **Skip blocks quietly.** The cursor advances only over the range actually
  scanned. If a run fails halfway the cursor stays where the last successful
  chunk ended, and the next run re-reads from there.
- **Claim history it never read.** On an empty database the cursor starts near
  the head, not at the launchpad's first block. Everything before that is
  simply not in the dataset, and the cursor says where the edge is.
- **Spend the node's patience.** One budget covers new launches and rechecks
  together; whatever it does not reach is left for the next run and counted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models import ChainCursor, LaunchpadLaunch
from app.models.base import as_utc
from app.providers.base import ProviderNotConfigured
from app.providers.launchpad import (
    EvmLaunchpadProvider,
    LaunchpadCallFailed,
    MigratedToken,
)

CURSOR_NAME = "launchpad-launches"


@dataclass
class ScanReport:
    """What one pass actually did. Every number is a count of work done."""

    from_block: int = 0
    to_block: int = 0
    blocks_scanned: int = 0
    launches_found: int = 0
    launches_new: int = 0
    status_calls: int = 0
    graduated: int = 0
    unreadable: int = 0
    """Contracts that reverted. Recorded as unanswered, never as a negative."""
    unchecked: int = 0
    """Launches the call budget did not reach. The difference between "none
    graduated" and "we stopped asking"."""
    behind_blocks: int = 0
    """How far the cursor still trails the head after this run."""
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_block": self.from_block,
            "to_block": self.to_block,
            "blocks_scanned": self.blocks_scanned,
            "launches_found": self.launches_found,
            "launches_new": self.launches_new,
            "status_calls": self.status_calls,
            "graduated": self.graduated,
            "unreadable": self.unreadable,
            "unchecked": self.unchecked,
            "behind_blocks": self.behind_blocks,
            "error": self.error,
        }


@dataclass
class ScanResult:
    report: ScanReport = field(default_factory=ScanReport)
    migrations: list[MigratedToken] = field(default_factory=list)
    """Tokens this pass found complete for the first time."""


async def _cursor(session: AsyncSession, chain: str) -> ChainCursor | None:
    return await session.scalar(
        select(ChainCursor).where(
            ChainCursor.chain == chain, ChainCursor.name == CURSOR_NAME
        )
    )


async def scan_launchpad(
    session: AsyncSession,
    *,
    settings: Settings | None = None,
    provider: EvmLaunchpadProvider | None = None,
    now: datetime | None = None,
) -> ScanResult:
    """Advance the cursor, record new launches, re-ask the unresolved ones."""
    settings = settings or get_settings()
    result = ScanResult()
    report = result.report
    moment = now or datetime.now(UTC)

    if provider is None:
        from app.providers.launchpad import get_launchpad_provider

        candidate = get_launchpad_provider(settings, settings.evm_chain)
        if not isinstance(candidate, EvmLaunchpadProvider):
            report.error = "no EVM launchpad is configured"
            return result
        provider = candidate

    chain = settings.evm_chain

    try:
        head = await provider.head_block()
    except (ProviderNotConfigured, LaunchpadCallFailed) as exc:
        report.error = f"{type(exc).__name__}: {exc}"
        return result

    cursor = await _cursor(session, chain)
    start = (
        cursor.block + 1
        if cursor is not None
        else max(0, head - settings.evm_scan_start_blocks_back)
    )
    end = min(head, start + settings.evm_scan_max_blocks_per_run - 1)
    report.from_block, report.to_block = start, end

    if start <= end:
        try:
            launches = await provider.scan_launches(start, end)
        except (ProviderNotConfigured, LaunchpadCallFailed) as exc:
            # The cursor does not move. A failed scan is a gap, and a gap that
            # was stepped over is indistinguishable from a quiet launchpad.
            report.error = f"{type(exc).__name__}: {exc}"
            report.behind_blocks = max(0, head - (cursor.block if cursor else start))
            return result

        report.blocks_scanned = end - start + 1
        report.launches_found = len(launches)
        for launch in launches:
            known = await session.scalar(
                select(LaunchpadLaunch).where(
                    LaunchpadLaunch.chain == chain,
                    LaunchpadLaunch.address == launch.address,
                )
            )
            if known is not None:
                continue
            session.add(
                LaunchpadLaunch(
                    chain=chain,
                    address=launch.address,
                    factory=launch.factory,
                    launched_at_block=launch.block,
                    graduated=None,
                    is_demo=False,
                )
            )
            report.launches_new += 1
        await session.flush()

        if cursor is None:
            session.add(
                ChainCursor(chain=chain, name=CURSOR_NAME, block=end, is_demo=False)
            )
        else:
            cursor.block = end
        await session.flush()

    report.behind_blocks = max(0, head - end)

    # Re-ask the unresolved ones, oldest first so nothing starves. A launch is
    # dropped from the rotation once it graduates or once the recheck window
    # closes — the row keeps NULL, which is "not known to have finished".
    horizon = moment - timedelta(hours=settings.evm_recheck_hours)
    pending = (
        await session.scalars(
            select(LaunchpadLaunch)
            .where(
                LaunchpadLaunch.chain == chain,
                LaunchpadLaunch.graduated.is_not(True),
                LaunchpadLaunch.created_at >= horizon,
            )
            .order_by(LaunchpadLaunch.created_at)
        )
    ).all()

    budget = settings.evm_launchpad_max_calls
    for launch in pending:
        if report.status_calls >= budget:
            report.unchecked += 1
            continue
        try:
            answer = await provider.graduation_status(launch.factory, launch.address)
        except LaunchpadCallFailed as exc:
            # Whatever is left stays pending. The node said nothing about it,
            # so neither does this row.
            report.error = f"{type(exc).__name__}: {exc}"
            report.unchecked += len(pending) - report.status_calls
            break
        report.status_calls += 1
        if answer is None:
            # The contract refused. Not a "no": the row is left as it was.
            report.unreadable += 1
            continue
        launch.checked_at = as_utc(moment)
        if answer:
            launch.graduated = True
            launch.graduated_at = as_utc(moment)
            report.graduated += 1
            result.migrations.append(MigratedToken(address=launch.address))
        else:
            launch.graduated = False

    await session.flush()
    return result
