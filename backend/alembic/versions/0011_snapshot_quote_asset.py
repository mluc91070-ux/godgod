"""token_snapshots: what the pool was quoted in.

A price is a ratio and this is the denominator. Two memes on one chain, one
quoted in the gas token and one in a tokenised share of Nvidia, are not the
same instrument: the second one's chart is not separable from Nvidia's without
the pair data, and the depth on the equity side is a constraint on the meme
side. The chain has a whole cohort of the second kind and this system was
recording them as if they were the first.

`quote_kind` is the classification, and it is stored per measurement rather
than per token on purpose: it describes the pool the price was taken from, and
a token can gain a deeper pool against a different asset. Held on the token, a
liquidity shift would rewrite the exposure of every historical row.

NULL is not `unknown`. NULL means the column did not exist when the row was
written; `unknown` means it did, this system looked, and the source said
nothing about the pair.

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("token_snapshots", schema=None) as batch:
        batch.add_column(sa.Column("quote_symbol", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("quote_address", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("quote_kind", sa.String(length=24), nullable=True))
        batch.create_index(batch.f("ix_token_snapshots_quote_kind"), ["quote_kind"])


def downgrade() -> None:
    with op.batch_alter_table("token_snapshots", schema=None) as batch:
        batch.drop_index(batch.f("ix_token_snapshots_quote_kind"))
        batch.drop_column("quote_kind")
        batch.drop_column("quote_address")
        batch.drop_column("quote_symbol")
