"""token_snapshots: why this measurement was taken.

A token used to be measured for exactly one reason — the promotion feed named
it this run — so the reason did not need recording. Retention adds a second
rule, and it is not a variation on the first: a retained token is measured
whether or not the feed still lists it, and it skips the liquidity and volume
floors that a discovered one must clear.

That matters because it is the whole point. A token that held a large market
cap and then drained is the most informative row in the dataset, and the
discovery floors would drop it precisely when it became interesting. Keeping it
is correct; keeping it *without saying so* would put two selection rules in one
column and make the population unreconstructible.

Existing rows are left NULL. They were all taken under discovery or migration,
but nothing recorded which, and writing a value now would be inventing a
provenance rather than reading one.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "token_snapshots", sa.Column("selected_by", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("token_snapshots", "selected_by")
