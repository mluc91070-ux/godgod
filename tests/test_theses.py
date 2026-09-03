"""Posed theses, and the rule that the file does not get to grade itself.

An argument written before the data exists is worth publishing. What is not
worth publishing is an argument that says how well it can be tested, because
that sentence is the one most likely to be optimistic and the one nobody
re-checks. So the file names the fields each link of its mechanism needs, and
the service counts them in the database.

The assertions here are all versions of that: a link whose fields are NULL on
every live row must come back `not-measured-here` with the zero attached; a
thesis is testable end to end only if every link is; fixtures must not be
counted, because the synthetic dataset has a holder count for every token and
this deployment has none.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest_asyncio

from app.models import Token, TokenSnapshot
from app.services.theses import (
    MEASURED,
    NOT_MEASURED,
    PARTLY_MEASURED,
    build_theses,
    read_theses,
)

AT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

THESIS = {
    "_meta": {"posed_by": "operator", "kind": "posed-theses"},
    "theses": [
        {
            "key": "demo-thesis",
            "title": "Does a thing cause another thing?",
            "claim": "it might",
            "posed_at": "2026-09-03",
            "argument": ["a sentence someone wrote"],
            "chain_of_causation": [
                {"step": "flow", "detail": "who is buying", "fields": ["buys", "sells"]},
                {"step": "depth", "detail": "does the pool hold", "fields": ["liquidity_usd"]},
                {"step": "who holds", "detail": "needs an indexer", "fields": ["holders"]},
            ],
            "falsification": "the gap is under the threshold",
            "confounds": [{"name": "sampling", "detail": "the frames differ"}],
        }
    ],
}


@pytest_asyncio.fixture
async def posed(tmp_path, settings):
    path = tmp_path / "theses.json"
    path.write_text(json.dumps(THESIS), encoding="utf-8")
    settings.theses_path = str(path)
    return settings


async def measured(session, **fields) -> None:
    token = Token(address="DEMOTHESIS" + "x" * 33, chain="solana", is_demo=False)
    session.add(token)
    await session.flush()
    session.add(
        TokenSnapshot(token_id=token.id, observed_at=AT, is_demo=False, **fields)
    )
    await session.flush()


async def test_a_link_with_no_rows_is_named_not_measured(session, posed) -> None:
    """The assertion the whole module exists for.

    A public node cannot count holders. The link that needs one must come back
    unmeasurable with the count attached, not quietly pass.
    """
    await measured(session, buys=10, sells=4, liquidity_usd=50_000.0)

    out = await build_theses(session, settings=posed)
    links = {link["step"]: link for link in out["theses"][0]["chain_of_causation"]}

    assert links["flow"]["status"] == MEASURED
    assert links["depth"]["status"] == MEASURED
    assert links["who holds"]["status"] == NOT_MEASURED
    assert links["who holds"]["measured_fields"] == {"holders": 0}


async def test_end_to_end_is_derived_not_declared(session, posed) -> None:
    await measured(session, buys=1, sells=1, liquidity_usd=1.0)

    thesis = (await build_theses(session, settings=posed))["theses"][0]
    assert thesis["testable_end_to_end"] is False
    assert thesis["blocked_at"] == ["who holds"]


async def test_a_half_measured_link_is_its_own_state(session, posed) -> None:
    """`partly-measured` is not `measured`.

    One of two fields present means the link can be looked at and not
    evaluated, and collapsing that into either neighbour loses the only
    information the reader needs.
    """
    await measured(session, buys=10, liquidity_usd=50_000.0)

    links = {
        link["step"]: link
        for link in (await build_theses(session, settings=posed))["theses"][0][
            "chain_of_causation"
        ]
    }
    assert links["flow"]["status"] == PARTLY_MEASURED
    assert links["flow"]["measured_fields"] == {"buys": 1, "sells": 0}


async def test_fixtures_do_not_count_as_capability(session, posed) -> None:
    """The synthetic dataset has a holder count for every token.

    Counting it here would report an indexer this deployment does not have —
    the exact shape of claiming a capability that is not implemented.
    """
    token = Token(address="DEMOFIXTURE" + "x" * 32, chain="solana", is_demo=True)
    session.add(token)
    await session.flush()
    session.add(
        TokenSnapshot(token_id=token.id, observed_at=AT, holders=900, is_demo=True)
    )
    await session.flush()

    out = await build_theses(session, settings=posed)
    links = {link["step"]: link for link in out["theses"][0]["chain_of_causation"]}
    assert links["who holds"]["status"] == NOT_MEASURED
    assert out["measurements"] == 0


async def test_a_field_that_is_not_a_column_is_named(session, posed, tmp_path) -> None:
    """A typo must not read as "measured and found empty"."""
    payload = json.loads(json.dumps(THESIS))
    payload["theses"][0]["chain_of_causation"][0]["fields"] = ["vibes"]
    path = tmp_path / "typo.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    posed.theses_path = str(path)

    links = {
        link["step"]: link
        for link in (await build_theses(session, settings=posed))["theses"][0][
            "chain_of_causation"
        ]
    }
    assert links["flow"]["unknown_fields"] == ["vibes"]
    assert links["flow"]["measured_fields"] == {}
    assert links["flow"]["status"] == NOT_MEASURED


async def test_no_file_is_a_state_not_a_failure(session, settings) -> None:
    settings.theses_path = "data/theses/definitely-not-here.json"
    out = await build_theses(session, settings=settings)
    assert out["theses"] == []
    assert "not a page that failed" in out["note"]


def test_the_shipped_thesis_parses_and_names_its_confounds() -> None:
    payload = read_theses("data/theses/chain-structure.json")
    assert payload is not None
    thesis = payload["theses"][0]

    # A thesis about a chain contrast that does not name the sampling
    # difference is a thesis that will confirm itself.
    names = " ".join(item["name"] for item in thesis["confounds"])
    assert "sampled" in names
    assert len(thesis["chain_of_causation"]) == 5
    assert thesis["falsification"]
