"""The collection loop, run by the application itself.

GitHub Actions was doing this on a fifteen-minute cron, and its scheduler is
best-effort. Measured on this repository over eleven hours: eight runs where
there should have been forty-four, with gaps of 208, 162 and 124 minutes. A
detector needs `OBSERVATION_MIN_SNAPSHOTS` measurements of the *same* token
before it can say anything, so a skipped run is not a late run — it is history
that never accumulates.

The instance is already always-on, so it can keep its own time. The GitHub
workflow stays as a backstop and the two cannot collide: the collector stores
one measurement per token per quarter hour and counts the second attempt as
`already_measured_this_slot`.

What this loop refuses to do:

- **Fail quietly.** Every cycle writes an `agent_runs` row through the same
  services the admin endpoints call. A loop that died would otherwise look
  exactly like a market where nothing happened.
- **Run in tests, or twice.** It starts only when `SCHEDULER_ENABLED` is on,
  and the task is held on the app so a second startup in the same process
  cannot create a second loop.
- **Take the process down.** An exception in one cycle is logged and the loop
  sleeps to the next tick. A market API having a bad minute must not stop
  measurement for the rest of the day.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.db.session import get_sessionmaker

logger = logging.getLogger(__name__)

SCHEDULER_TASK_ATTR = "godgod_scheduler_task"


async def run_cycle(settings: Settings | None = None) -> dict[str, object]:
    """One pass: measure, observe, research.

    Ordered, and the order matters. Observation reads what collection wrote,
    and research reads the anomalies observation found. Running them
    concurrently would mean each cycle worked on the previous cycle's data for
    no gain — the whole pass costs seconds.

    Each stage gets its own session so a failure in one does not roll back the
    work of the one before it. Measurements are the expensive part and must
    survive a research bug.
    """
    settings = settings or get_settings()
    sessionmaker = get_sessionmaker()
    summary: dict[str, object] = {}

    from app.services.chain import collect_chain

    async with sessionmaker() as session:
        report = await collect_chain(session, settings=settings)
        summary["chain"] = report.as_dict()

    # What people are looking up, sampled on the same clock as the pool. It is
    # its own session and its own failure: an attention source that is down or
    # rate-limited costs that series, never the measurements.
    from app.services.attention import collect_attention

    async with sessionmaker() as session:
        attention = await collect_attention(session, settings=settings)
        summary["attention"] = attention.as_dict()

    # Observation and research read the live tables only once the site has
    # stopped serving fixtures. Running them against the demo dataset on a
    # timer would re-derive the same synthetic observations every cycle.
    if not settings.demo_mode:
        from app.services.observation import ObservationPipeline

        async with sessionmaker() as session:
            observed = await ObservationPipeline(settings=settings).run(session)
            summary["observe"] = observed.as_dict()

        from app.services.research import run_research_cycle

        async with sessionmaker() as session:
            researched = await run_research_cycle(session, settings=settings)
            summary["research"] = researched.as_dict()

    return summary


def _seconds_to_next_tick(interval: int, now: datetime | None = None) -> float:
    """Align ticks to the wall clock rather than to process start.

    The collector keys a measurement to the quarter hour. A loop that started
    at 12:07 and slept 900s would fire at 12:22, land in the 12:15 slot, and
    then at 12:37 land in the 12:30 slot — every measurement arriving late in
    its window, and any restart shifting the whole series again.
    """
    now = now or datetime.now(UTC)
    seconds_into_hour = now.minute * 60 + now.second + now.microsecond / 1e6
    remainder = seconds_into_hour % interval
    return interval - remainder if remainder else float(interval)


async def _loop(settings: Settings) -> None:
    interval = max(60, settings.scheduler_interval_seconds)
    logger.info("scheduler: started, every %ss", interval)

    while True:
        await asyncio.sleep(_seconds_to_next_tick(interval))
        try:
            summary = await run_cycle(settings)
            chain = summary.get("chain") or {}
            logger.info(
                "scheduler cycle: %s measurements, %s migrations%s",
                chain.get("snapshots_stored"),
                chain.get("migrations_seen"),
                "" if chain.get("complete") else " (incomplete)",
            )
        except asyncio.CancelledError:
            logger.info("scheduler: stopping")
            raise
        except Exception:
            # Logged with the traceback, never swallowed into a count. The next
            # tick still fires: one bad minute at a data source must not end
            # measurement for the day.
            logger.exception("scheduler: cycle failed")


def start(app) -> None:
    """Attach the loop to the running app, once."""
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("scheduler: disabled (SCHEDULER_ENABLED is off)")
        return
    if getattr(app.state, SCHEDULER_TASK_ATTR, None) is not None:
        return
    task = asyncio.create_task(_loop(settings), name="godgod-scheduler")
    setattr(app.state, SCHEDULER_TASK_ATTR, task)


async def stop(app) -> None:
    task = getattr(app.state, SCHEDULER_TASK_ATTR, None)
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    setattr(app.state, SCHEDULER_TASK_ATTR, None)
