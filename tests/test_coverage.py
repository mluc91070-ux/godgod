"""Field coverage: the grading half of a posed thesis.

An argument about a mechanism names the fields its steps would need. Something
has to say whether those fields hold anything, and that something must be the
database rather than the argument — otherwise the claim grades itself.

Three properties, and each is a way the grade could quietly become useless:

- fixtures are excluded, because the synthetic dataset carries a holder count
  for every token and this deployment has no indexer;
- a field with no rows reports zero rather than being left out, because an
  absent key cannot distinguish "we looked" from "nobody asked";
- every gradable column is present in every answer, so a link naming one can
  always be graded rather than falling through to "unknown field".
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.models import Token, TokenSnapshot
from app.services.coverage import COVERED_FIELDS, build_coverage

AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


async def add(session, *, chain="solana", demo=False, tag="A", **fields) -> None:
    token = Token(address=f"DEMOCOV{tag}" + "x" * 33, chain=chain, is_demo=demo)
    session.add(token)
    await session.flush()
    session.add(TokenSnapshot(token_id=token.id, observed_at=AT, is_demo=demo, **fields))
    await session.flush()


async def test_a_field_with_no_rows_reports_zero(session) -> None:
    """The assertion this module exists for.

    A public node cannot count holders. `holders` must come back as a zero, not
    as a missing key: an argument resting on holder behaviour has to be gradable
    as untestable, and an absent key grades as nothing at all.
    """
    await add(session, buys=10, sells=4, liquidity_usd=50_000.0)

    out = await build_coverage(session)

    assert out["fields"]["holders"] == 0
    assert out["fields"]["buys"] == 1
    assert out["fields"]["liquidity_usd"] == 1
    assert out["measurements"] == 1


async def test_every_gradable_column_is_always_answered(session) -> None:
    out = await build_coverage(session)
    assert set(out["fields"]) == set(COVERED_FIELDS)
    assert all(count == 0 for count in out["fields"].values())
    assert out["measurements"] == 0


async def test_fixtures_are_not_a_capability(session) -> None:
    """The synthetic dataset has a holder count for every token.

    Counting it would report an indexer this deployment does not have, which is
    the exact shape of claiming an unimplemented capability.
    """
    await add(session, demo=True, tag="D", holders=900, liquidity_usd=1.0)

    out = await build_coverage(session)
    assert out["fields"]["holders"] == 0
    assert out["measurements"] == 0
    assert out["chains"] == {}


async def test_the_chains_are_counted_apart(session) -> None:
    """A contrast between two chains needs both of them present."""
    await add(session, tag="S", chain="solana", buys=1)
    await add(session, tag="R", chain="robinhood", buys=1)

    out = await build_coverage(session)
    assert out["chains"] == {"solana": 1, "robinhood": 1}


async def test_the_quote_column_is_gradable(session) -> None:
    """Newer columns are graded like any other, so a thesis naming one is not
    silently ungradable because the column post-dates most of the series."""
    await add(session, quote_kind="gas", quote_symbol="WETH")

    out = await build_coverage(session)
    assert out["fields"]["quote_kind"] == 1
    assert out["fields"]["quote_symbol"] == 1
