"""Posed theses, and how far the data can carry each one.

A thesis is an argument about a mechanism, written before the measurements
exist to settle it. It is not a hypothesis — nothing here has a dataset, a
horizon or a verdict — and it is not a finding. Writing one down is still
worth doing, because it commits to an explanation before the result is known
and can be checked later against numbers nobody had chosen yet.

The one thing this module refuses to do is let the file grade itself.

A mechanism is a chain of steps, and a chain is exactly as testable as its
weakest link. So the file names the fields each link needs, and **this module
goes and counts them** — how many live measurements actually carry a value for
each. `holders` is NULL on every live row, because a public node cannot count
holders without an indexer, and two of the five links in the standing thesis
depend on it. That is reported as a measured fact about the database rather
than as an admission somebody remembered to write down.

The same applies to the arms. A thesis that contrasts two chains needs both of
them present, so the per-chain counts come from the rows, and a contrast with
one empty side is named as such before anyone reads a difference into it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.untrusted import sanitize_external_text
from app.models import Token, TokenSnapshot

MEASURED = "measured"
PARTLY_MEASURED = "partly-measured"
NOT_MEASURED = "not-measured-here"
"""Three states, and the third is not a failure.

`not-measured-here` says this deployment cannot see that link — no indexer, no
per-wallet history. A thesis with an unmeasurable link is still worth
publishing; it just cannot be tested end to end, and saying so is the whole
point of decomposing it.
"""

SNAPSHOT_FIELDS = {
    "holders",
    "holder_concentration_top10",
    "buys",
    "sells",
    "liquidity_usd",
    "volume_usd",
    "market_cap_usd",
    "fdv_usd",
    "transactions",
    "age_seconds",
    "quote_kind",
}
"""Fields a thesis is allowed to name. A link asking for something that is not
a column gets `unknown_field` rather than a silent zero — a typo in the file
must not read as "this was measured and found empty"."""


@dataclass
class LinkCoverage:
    step: str
    detail: str
    fields: list[str]
    measured_fields: dict[str, int]
    """Per field, how many live measurements carry a value."""
    unknown_fields: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        known = [name for name in self.fields if name not in self.unknown_fields]
        if not known:
            return NOT_MEASURED
        present = [name for name in known if self.measured_fields.get(name, 0) > 0]
        if len(present) == len(known):
            return MEASURED
        return PARTLY_MEASURED if present else NOT_MEASURED

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "detail": self.detail,
            "fields": self.fields,
            "measured_fields": self.measured_fields,
            "unknown_fields": self.unknown_fields,
            "status": self.status,
        }


def read_theses(path: str) -> dict[str, Any] | None:
    """The file, or None when there is none.

    Synchronous and outside the async path, like the watchlist notes: it is
    read once per request and a missing file is a valid state, never a reason
    for a request to fail.
    """
    source = Path(path)
    if not source.exists():
        return None
    return json.loads(source.read_text(encoding="utf-8"))


async def _field_coverage(session: AsyncSession, names: set[str]) -> dict[str, int]:
    """How many live measurements carry a value for each named field.

    One query per field, over live rows only. Fixtures are excluded on purpose:
    the synthetic dataset has a holder count for every token, and counting it
    here would report a capability this deployment does not have.
    """
    coverage: dict[str, int] = {}
    for name in sorted(names):
        column = getattr(TokenSnapshot, name)
        coverage[name] = int(
            await session.scalar(
                select(func.count())
                .select_from(TokenSnapshot)
                .where(TokenSnapshot.is_demo.is_(False), column.is_not(None))
            )
            or 0
        )
    return coverage


async def build_theses(
    session: AsyncSession, *, settings: Settings | None = None
) -> dict[str, Any]:
    """Every posed thesis, with each link graded against the database."""
    settings = settings or get_settings()
    payload = read_theses(settings.theses_path)
    if payload is None:
        return {
            "theses": [],
            "measurements": 0,
            "chains": {},
            "note": (
                "No theses are on file. That is a real state of this deployment, "
                "not a page that failed to load."
            ),
        }

    entries = payload.get("theses") or []
    wanted: set[str] = set()
    for entry in entries:
        for link in entry.get("chain_of_causation") or []:
            wanted.update(name for name in (link.get("fields") or []) if name in SNAPSHOT_FIELDS)

    coverage = await _field_coverage(session, wanted)
    measurements = int(
        await session.scalar(
            select(func.count()).select_from(TokenSnapshot).where(TokenSnapshot.is_demo.is_(False))
        )
        or 0
    )
    chains = {
        str(chain): int(count)
        for chain, count in (
            await session.execute(
                select(Token.chain, func.count())
                .where(Token.is_demo.is_(False))
                .group_by(Token.chain)
            )
        ).all()
    }

    rendered = []
    for entry in entries:
        links = []
        for link in entry.get("chain_of_causation") or []:
            names = [str(name) for name in (link.get("fields") or [])]
            unknown = [name for name in names if name not in SNAPSHOT_FIELDS]
            links.append(
                LinkCoverage(
                    step=sanitize_external_text(str(link.get("step") or ""), max_len=128),
                    detail=sanitize_external_text(str(link.get("detail") or ""), max_len=400),
                    fields=names,
                    measured_fields={
                        name: coverage.get(name, 0) for name in names if name not in unknown
                    },
                    unknown_fields=unknown,
                ).as_dict()
            )

        rendered.append(
            {
                "key": sanitize_external_text(str(entry.get("key") or ""), max_len=64),
                "title": sanitize_external_text(str(entry.get("title") or ""), max_len=300),
                "claim": sanitize_external_text(str(entry.get("claim") or ""), max_len=600),
                "posed_at": entry.get("posed_at"),
                "posed_by": payload.get("_meta", {}).get("posed_by", "operator"),
                "argument": [
                    sanitize_external_text(str(line), max_len=1200)
                    for line in (entry.get("argument") or [])
                ],
                "chain_of_causation": links,
                "falsification": sanitize_external_text(
                    str(entry.get("falsification") or ""), max_len=1200
                ),
                "confounds": [
                    {
                        "name": sanitize_external_text(str(item.get("name") or ""), max_len=200),
                        "detail": sanitize_external_text(
                            str(item.get("detail") or ""), max_len=1200
                        ),
                    }
                    for item in (entry.get("confounds") or [])
                ],
                # Derived, not declared. A thesis is testable end to end only if
                # every link is, and the file does not get a vote on that.
                "testable_end_to_end": all(
                    link["status"] == MEASURED for link in links
                )
                and bool(links),
                "blocked_at": [
                    link["step"] for link in links if link["status"] != MEASURED
                ],
            }
        )

    return {
        "theses": rendered,
        "measurements": measurements,
        "chains": chains,
        "note": (
            "A thesis is an argument, not a result. Nothing here was produced by an "
            "experiment, and the status beside each link is counted from the live "
            "measurements rather than claimed by the file."
        ),
    }
