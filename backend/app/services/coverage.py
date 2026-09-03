"""How much of each measured field this deployment actually has.

One question, asked of the database: for every column a snapshot can carry, how
many live measurements carry a value for it. That is all this module does, and
the narrowness is the point.

It exists because arguments about mechanisms need grading and must not grade
themselves. A thesis names the fields its steps would need; something has to
say whether those fields hold anything, and that something has to be the
database rather than the file making the claim. `holders` is NULL on every live
row — a public node cannot count holders without an indexer — so any argument
resting on holder behaviour is untestable here, and this is where that stops
being an opinion and becomes a count.

Two rules it does not bend:

- **Fixtures do not count.** The synthetic dataset carries a holder count for
  every token. Including it would report an indexer this deployment does not
  have, which is exactly the shape of claiming an unimplemented capability.
- **A column with zero rows is reported as zero, never omitted.** An absent key
  and a zero are different answers, and a reader who gets an absent key cannot
  tell "we looked and found none" from "nobody asked".
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Token, TokenSnapshot

COVERED_FIELDS: tuple[str, ...] = (
    "market_cap_usd",
    "fdv_usd",
    "liquidity_usd",
    "volume_usd",
    "holders",
    "holder_concentration_top10",
    "transactions",
    "buys",
    "sells",
    "age_seconds",
    "quote_kind",
    "quote_symbol",
)
"""Every snapshot column worth grading against. Fixed here rather than derived
from the model, so adding a column is a decision to publish its coverage rather
than a side effect of adding it."""


async def build_coverage(session: AsyncSession) -> dict[str, Any]:
    """Per field, how many live measurements carry a value."""
    live = int(
        await session.scalar(
            select(func.count())
            .select_from(TokenSnapshot)
            .where(TokenSnapshot.is_demo.is_(False))
        )
        or 0
    )

    fields: dict[str, int] = {}
    for name in COVERED_FIELDS:
        column = getattr(TokenSnapshot, name)
        fields[name] = int(
            await session.scalar(
                select(func.count())
                .select_from(TokenSnapshot)
                .where(TokenSnapshot.is_demo.is_(False), column.is_not(None))
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

    return {
        "measurements": live,
        "fields": fields,
        "chains": chains,
        "note": (
            "Live measurements only. The synthetic dataset carries a holder count "
            "for every token and is excluded, because counting it would report an "
            "indexer this deployment does not have."
        ),
    }
