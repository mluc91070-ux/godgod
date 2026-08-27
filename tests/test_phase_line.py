"""The line that describes the system, on every page.

It was a constant, and it said "still serving the demo dataset" for eight
minutes after the demo dataset was deleted. One string, wrong everywhere at
once — the exact failure a hardcoded status invites. These tests pin it to the
facts it claims.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.routes.system import describe_phase
from app.models import Token, TokenSnapshot


async def _store(session, hours_ago: float, *, is_demo: bool = False) -> None:
    token = await session.scalar(select(Token).where(Token.address == "PhaseTest111"))
    if token is None:
        token = Token(address="PhaseTest111", symbol="PHS", is_demo=is_demo)
        session.add(token)
        await session.flush()
    session.add(
        TokenSnapshot(
            token_id=token.id,
            observed_at=datetime.now(UTC) - timedelta(hours=hours_ago),
            liquidity_usd=50_000.0,
            source="test",
            is_demo=is_demo,
        )
    )
    await session.flush()


async def test_demo_mode_says_so(session, settings) -> None:
    settings.demo_mode = True
    await _store(session, 100.0)
    line = await describe_phase(session, settings)
    assert "demo dataset" in line
    assert "researching real tokens" not in line


async def test_no_measurement_is_not_dressed_up_as_research(session, settings) -> None:
    """Live with an empty table is a real state and has to read as one."""
    settings.demo_mode = False
    line = await describe_phase(session, settings)
    assert "no measurement stored yet" in line
    assert "demo dataset" not in line


async def test_a_young_dataset_says_it_cannot_conclude(session, settings) -> None:
    """This is why every result reads INCONCLUSIVE, and the page should say it."""
    settings.demo_mode = False
    await _store(session, 3.0)
    line = await describe_phase(session, settings)
    assert "3 hours" in line
    assert "too little to conclude" in line


async def test_one_hour_is_singular(session, settings) -> None:
    settings.demo_mode = False
    await _store(session, 1.2)
    assert "1 hour of history" in await describe_phase(session, settings)


async def test_a_mature_dataset_drops_the_caveat(session, settings) -> None:
    settings.demo_mode = False
    await _store(session, 24 * 9 + 1)
    line = await describe_phase(session, settings)
    assert "9 days of history" in line
    assert "too little to conclude" not in line


async def test_demo_rows_never_age_the_live_dataset(session, settings) -> None:
    """A fixture dated last year would otherwise claim a year of real history."""
    settings.demo_mode = False
    await _store(session, 24 * 300, is_demo=True)
    await _store(session, 2.0)
    line = await describe_phase(session, settings)
    assert "2 hours" in line
    assert "days" not in line


@pytest.mark.parametrize("hours", [0.0, 0.4, 0.9])
async def test_a_dataset_minutes_old_never_reports_negative_or_odd(
    session, settings, hours
) -> None:
    settings.demo_mode = False
    await _store(session, hours)
    line = await describe_phase(session, settings)
    assert "0 hours of history" in line
    assert "-" not in line.split("history")[0]
