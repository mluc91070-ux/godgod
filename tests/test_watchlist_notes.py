"""The operator's notes: stored, attributed, and unable to become a result.

Writing down what a person believes about a token is not fabricating research.
Letting that belief reach a dataset, a detector or a verdict would be. This
file is the line between the two, and it checks the line rather than the prose.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.enums import MemoryType
from app.models import Anomaly, Experiment, Hypothesis, Memory, Observation
from app.services.memory import store_memory

NOTES = Path(__file__).resolve().parents[1] / "data" / "watchlist" / "robinhood-runners.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(NOTES.read_text(encoding="utf-8"))


# -- the file itself --------------------------------------------------------


def test_the_notes_declare_what_they_are(payload) -> None:
    meta = payload["_meta"]
    assert meta["is_demo"] is False
    assert meta["kind"] == "operator-notes"
    assert meta["supplied_by"] == "operator"
    assert "not research" in meta["note"]


def test_every_note_keeps_the_claim_and_the_measurement_apart(payload) -> None:
    """One token's supplied figure was more than fifty percent off.

    That is the reason the two are separate fields and never one.
    """
    for entry in payload["tokens"]:
        assert entry["claimed_market_cap"], entry["symbol"]
        assert isinstance(entry["measured_market_cap_usd"], (int, float)), entry["symbol"]


def test_every_note_has_an_address_and_a_why(payload) -> None:
    for entry in payload["tokens"]:
        assert entry["address"].startswith("0x") and len(entry["address"]) == 42
        assert entry["lore"].strip()
        assert entry["why"].strip()


def test_no_note_predicts_a_price(payload) -> None:
    """The voice rules apply to text this system publishes, whoever wrote it."""
    banned = ("will go", "guaranteed", "100x", "buy now", "bullish", "to the moon")
    for entry in payload["tokens"]:
        blob = f"{entry['lore']} {entry['why']}".lower()
        for phrase in banned:
            assert phrase not in blob, f"{entry['symbol']}: {phrase}"


def test_the_addresses_are_unique(payload) -> None:
    addresses = [entry["address"].lower() for entry in payload["tokens"]]
    assert len(addresses) == len(set(addresses))


# -- what storing one may and may not do ------------------------------------


async def test_a_note_is_stored_attributed_and_untested(session) -> None:
    result = await store_memory(
        session,
        memory_type=str(MemoryType.TOKEN),
        content="a note about a token, and an untested claim about why it ran",
        summary="TOK on robinhood — an operator note, not a finding",
        source="operator-note",
        confidence=None,
        meta={"address": "0x" + "a" * 40, "tested": False},
        is_demo=False,
        commit=False,
    )

    assert result.created
    stored = result.memory
    assert stored.source == "operator-note", "provenance is on the row, not in the prose"
    assert stored.confidence is None, "this system does not rate a claim it has not tested"
    assert stored.meta["tested"] is False
    assert stored.is_demo is False


async def test_storing_notes_writes_nothing_that_looks_like_research(session) -> None:
    """The assertion this file exists for.

    A note is a note. If storing one could also produce an observation, an
    anomaly, a hypothesis or an experiment, the difference between what a
    person believes and what the system measured would stop being visible.
    """
    await store_memory(
        session,
        memory_type=str(MemoryType.TOKEN),
        content="another note about another token",
        summary="a note",
        source="operator-note",
        is_demo=False,
        commit=False,
    )

    for model in (Observation, Anomaly, Hypothesis, Experiment):
        rows = (await session.scalars(select(model))).all()
        assert not [row for row in rows if not row.is_demo], model.__name__


async def test_notes_are_distinguishable_from_derived_memories(session) -> None:
    """Both land under the same type, so the source is what separates them."""
    await store_memory(
        session,
        memory_type=str(MemoryType.TOKEN),
        content="a note somebody wrote",
        source="operator-note",
        is_demo=False,
        commit=False,
    )
    await store_memory(
        session,
        memory_type=str(MemoryType.TOKEN),
        content="something this system derived about a token",
        source="observation-pipeline",
        is_demo=False,
        commit=False,
    )

    rows = (
        await session.scalars(
            select(Memory).where(Memory.memory_type == str(MemoryType.TOKEN))
        )
    ).all()
    hand = [row for row in rows if row.source == "operator-note"]
    derived = [row for row in rows if row.source != "operator-note"]
    assert len(hand) == 1 and len(derived) == 1
