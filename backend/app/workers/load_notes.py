"""Store the operator's notes about the watchlist as memories.

These are notes a person wrote: what each token is, and why they think it ran.
They are not observations and they are not results, and the difference is
enforced here rather than left to whoever reads the page:

- they go in as `MemoryType.TOKEN` with `source="operator-note"`, so every
  surface can tell them apart from anything the system derived;
- the text is sanitised on the way in, like any third-party string;
- a `ResearchSource` of kind MANUAL records where they came from;
- no observation, anomaly, hypothesis or experiment is written, and
  `research/dataset.py` already drops watchlist tokens by name, so nothing
  here can reach a comparison.

The numbers are kept in two separate fields on purpose. `claimed_market_cap`
is the operator's figure and `measured_market_cap_usd` is what the market
source said when the file was written. On one of them they disagreed by more
than fifty percent, which is the whole reason they are not merged.

One field on each entry is not an opinion at all: what the deepest pool is
priced in. It is read from the source, it is the only part of a note that a
detector also measures independently, and it is rendered last so a reader can
see the one checkable fact in a paragraph of claims.

Run:  cd backend && .venv/Scripts/python -m app.workers.load_notes
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.enums import MemoryType
from app.core.untrusted import sanitize_external_text
from app.models import ResearchSource
from app.services.memory import store_memory

SOURCE = "operator-note"


def render(entry: dict, chain: str) -> tuple[str, str]:
    """One memory: what it is, why someone thinks it ran, and what it measured.

    The claim and the measurement sit in the same sentence rather than in two
    places, because a reader who sees only one of them is being told half of
    something.
    """
    symbol = sanitize_external_text(str(entry.get("symbol") or ""), max_len=32)
    lore = sanitize_external_text(str(entry.get("lore") or ""), max_len=600)
    why = sanitize_external_text(str(entry.get("why") or ""), max_len=1200)
    claimed = sanitize_external_text(str(entry.get("claimed_market_cap") or ""), max_len=64)
    measured = entry.get("measured_market_cap_usd")
    quote = sanitize_external_text(str(entry.get("measured_quote_symbol") or ""), max_len=32)
    quote_kind = sanitize_external_text(str(entry.get("measured_quote_kind") or ""), max_len=32)

    summary = f"{symbol} on {chain} — an operator note, not a finding"
    body = (
        f"{lore}\n\n"
        f"why it ran, as claimed and untested: {why}\n\n"
        f"market cap when this note was filed: ${measured:,.0f} measured; "
        f"{claimed} as supplied. nothing here has been tested by any experiment "
        f"in this system, and the token is excluded from every dataset because a "
        f"list of tokens chosen after they ran is a list of survivors."
    )
    if quote:
        # The one line in a note that was measured rather than asserted. An
        # equity denominator is a structural fact about the pool, and it is
        # the exposure of an open hypothesis — which this token is excluded
        # from, for the same reason every other claim here is untested.
        kind = f", which is {quote_kind.replace('-', ' ')}" if quote_kind else ""
        body += f"\n\npriced in {quote}{kind}. that part is measured, not claimed."
    return summary, body


def read_notes(path: str) -> dict | None:
    """The file, or None when there is none.

    Absent is a valid state — a deployment with no notes has none — and it must
    never be the reason a container fails to start. Read synchronously and
    outside the async path: it happens once, before anything is awaited.
    """
    notes = Path(path)
    if not notes.exists():
        return None
    return json.loads(notes.read_text(encoding="utf-8"))


async def main() -> int:
    settings = get_settings()
    payload = read_notes(settings.watchlist_notes_path)
    if payload is None:
        print(f"[skip] no watchlist notes at {settings.watchlist_notes_path}")
        return 0
    chain = payload["chain"]
    entries = payload["tokens"]

    engine = create_async_engine(settings.database_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    created = 0
    async with maker() as session:
        known = await session.scalar(
            select(ResearchSource).where(ResearchSource.name == SOURCE)
        )
        if known is None:
            session.add(
                ResearchSource(
                    kind="MANUAL",
                    name=SOURCE,
                    url=None,
                    description=(
                        "Notes written by the operator about tokens on the watchlist: "
                        "what each one is and why they believe it ran. Untested claims, "
                        "kept apart from anything this system measured or derived."
                    ),
                    reliability=None,
                    is_demo=False,
                )
            )
            await session.flush()

        for entry in entries:
            summary, body = render(entry, chain)
            result = await store_memory(
                session,
                memory_type=str(MemoryType.TOKEN),
                content=body,
                summary=summary,
                source=SOURCE,
                # No confidence. A number here would be this system rating a
                # claim it has not tested.
                confidence=None,
                meta={
                    "chain": chain,
                    "address": entry["address"],
                    "symbol": entry.get("symbol"),
                    "supplied_by": payload["_meta"]["supplied_by"],
                    "claimed_market_cap": entry.get("claimed_market_cap"),
                    "measured_market_cap_usd": entry.get("measured_market_cap_usd"),
                    "measured_liquidity_usd": entry.get("measured_liquidity_usd"),
                    "measured_volume_24h_usd": entry.get("measured_volume_24h_usd"),
                    "measured_at": payload["_meta"]["measured_at"],
                    "tested": False,
                },
                is_demo=False,
                commit=False,
            )
            created += 1 if result.created else 0
        await session.commit()

    await engine.dispose()
    held = len(entries) - created
    print(f"[ok  ] {len(entries)} notes read, {created} stored, {held} already held")
    print("       stored as MemoryType.TOKEN with source=operator-note")
    print("       no observation, anomaly, hypothesis or experiment was written")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
