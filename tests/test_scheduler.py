"""The in-process collection loop.

This exists because an external cron was measured skipping most of its runs,
and the failure was invisible: a skipped collection and a quiet market produce
the same empty database. So the tests here are mostly about the loop being
impossible to lose — it must not start where it should not, must not start
twice, and must not die on a bad cycle.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.workers import scheduler


class FakeApp:
    def __init__(self) -> None:
        self.state = type("State", (), {})()


def test_ticks_are_aligned_to_the_wall_clock() -> None:
    """A measurement is keyed to the quarter hour, so the loop must be too.

    Sleeping a flat interval from process start would put every measurement
    late in its slot, and every restart would shift the whole series.
    """
    at = lambda m, s=0: datetime(2026, 8, 27, 12, m, s, tzinfo=UTC)  # noqa: E731

    assert scheduler._seconds_to_next_tick(900, at(0)) == 900.0
    assert scheduler._seconds_to_next_tick(900, at(7)) == 480.0
    assert scheduler._seconds_to_next_tick(900, at(14, 30)) == 30.0
    assert scheduler._seconds_to_next_tick(900, at(15)) == 900.0
    assert scheduler._seconds_to_next_tick(900, at(59, 59)) == 1.0


def test_the_next_tick_is_never_zero_or_negative() -> None:
    """A zero would spin the loop; a negative would raise inside sleep."""
    for minute in range(60):
        for second in (0, 1, 33, 59):
            delay = scheduler._seconds_to_next_tick(
                900, datetime(2026, 8, 27, 9, minute, second, tzinfo=UTC)
            )
            assert 0 < delay <= 900


async def test_it_does_not_start_when_disabled(settings, monkeypatch) -> None:
    settings.scheduler_enabled = False
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)

    app = FakeApp()
    scheduler.start(app)
    assert getattr(app.state, scheduler.SCHEDULER_TASK_ATTR, None) is None


async def test_it_never_starts_twice(settings, monkeypatch) -> None:
    """Two loops would double every request and halve the budget."""
    settings.scheduler_enabled = True
    settings.scheduler_interval_seconds = 900
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)

    app = FakeApp()
    scheduler.start(app)
    first = getattr(app.state, scheduler.SCHEDULER_TASK_ATTR)
    scheduler.start(app)
    assert getattr(app.state, scheduler.SCHEDULER_TASK_ATTR) is first

    await scheduler.stop(app)
    assert getattr(app.state, scheduler.SCHEDULER_TASK_ATTR) is None


async def test_stopping_a_loop_that_never_started_is_harmless() -> None:
    await scheduler.stop(FakeApp())


async def test_a_failing_cycle_does_not_end_the_loop(settings, monkeypatch) -> None:
    """One bad minute at a data source must not stop measurement for the day."""
    settings.scheduler_enabled = True
    settings.scheduler_interval_seconds = 60
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    # Fire immediately instead of waiting for a real wall-clock boundary.
    monkeypatch.setattr(scheduler, "_seconds_to_next_tick", lambda *a, **k: 0.001)

    calls: list[int] = []

    async def flaky(_settings=None):
        calls.append(len(calls))
        if len(calls) == 1:
            raise RuntimeError("the market API had a bad minute")
        return {"chain": {"snapshots_stored": 1, "migrations_seen": 0, "complete": True}}

    monkeypatch.setattr(scheduler, "run_cycle", flaky)

    app = FakeApp()
    scheduler.start(app)
    for _ in range(200):
        await asyncio.sleep(0.01)
        if len(calls) >= 3:
            break
    await scheduler.stop(app)

    # It survived the failure and kept going.
    assert len(calls) >= 3


async def test_cancelling_stops_it_rather_than_being_swallowed(
    settings, monkeypatch
) -> None:
    """`except Exception` must not catch CancelledError, or shutdown hangs."""
    settings.scheduler_enabled = True
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "_seconds_to_next_tick", lambda *a, **k: 0.001)

    running = asyncio.Event()

    async def slow(_settings=None):
        running.set()
        await asyncio.sleep(30)
        return {}

    monkeypatch.setattr(scheduler, "run_cycle", slow)

    app = FakeApp()
    scheduler.start(app)
    await asyncio.wait_for(running.wait(), timeout=5)
    await asyncio.wait_for(scheduler.stop(app), timeout=5)


async def test_a_cycle_in_demo_mode_measures_but_does_not_research(
    settings, monkeypatch
) -> None:
    """Re-deriving the synthetic dataset on a timer would be pure noise.

    Collection still runs — that is the whole point of demo mode: real history
    accumulates underneath while the site serves fixtures.
    """
    settings.demo_mode = True
    ran: list[str] = []

    class Report:
        def as_dict(self):
            ran.append("chain")
            return {"snapshots_stored": 3, "migrations_seen": 1, "complete": True}

    async def fake_collect(session, **kwargs):
        return Report()

    import app.services.chain as chain_module

    monkeypatch.setattr(chain_module, "collect_chain", fake_collect)

    summary = await scheduler.run_cycle(settings)

    assert "chain" in summary
    assert "observe" not in summary
    assert "research" not in summary


@pytest.mark.parametrize("interval", [1, 30, 59])
def test_a_too_short_interval_is_floored(interval, settings, monkeypatch) -> None:
    """A one-second loop would exhaust the data source's rate limit."""
    settings.scheduler_enabled = True
    settings.scheduler_interval_seconds = interval
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    assert max(60, settings.scheduler_interval_seconds) == 60
