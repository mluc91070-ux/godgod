"""token_snapshots: fully diluted valuation, apart from market cap.

The market adapter read `marketCap or fdv` into `market_cap_usd`. When the
source had no market cap for a token — common for a freshly migrated one — the
fully diluted valuation was stored under a field the site labels "market cap".
Those are two different numbers, separated by the supply that has not been
minted, and on a low-float token they differ by an order of magnitude.

An external audit found it from the outside without seeing this code: market
cap over liquidity came out between 90x and 145x on several tokens, which is
what an FDV compared against a real pool looks like.

Existing rows are not backfilled or corrected. There is no record of which of
the two each stored value was, and guessing per row would replace a known
mislabel with an invented one. From here the two are collected separately;
before here, `market_cap_usd` is "market cap or FDV, unrecorded which", and
that is what it will stay.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("token_snapshots", sa.Column("fdv_usd", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("token_snapshots", "fdv_usd")
