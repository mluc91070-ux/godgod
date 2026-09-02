"""attention_snapshots: what people are looking up, as a series.

The social collector is gone; what it was for is not. A pool says what happened
in it and nothing about whether anyone was paying attention, which is what the
social series was for and why three detectors lost their source with it.

A search ranking is a better measurement than the one it replaces. It reports
positions rather than sentiment — a coin is in the list at a rank at a time —
so it is countable, comparable, and has no model anywhere near it.

Two columns carry the whole design. `rank` is the measurement, and a coin
absent from the ranking gets no row at all: "not ranked" and "ranked last" are
different facts and only the first is true. `token_id` is set on an exact
contract-address match and nothing else, because symbols collide by the dozen
across chains and a wrong link puts someone else's attention on a real token's
record.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attention_snapshots",
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ref", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("market_cap_rank", sa.Integer(), nullable=True),
        sa.Column("chain", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=64), nullable=True),
        sa.Column("token_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("attention_snapshots", schema=None) as batch:
        batch.create_index(batch.f("ix_attention_snapshots_observed_at"), ["observed_at"])
        batch.create_index(batch.f("ix_attention_snapshots_ref"), ["ref"])
        batch.create_index(batch.f("ix_attention_snapshots_address"), ["address"])
        batch.create_index(batch.f("ix_attention_snapshots_token_id"), ["token_id"])
        batch.create_index(batch.f("ix_attention_snapshots_is_demo"), ["is_demo"])


def downgrade() -> None:
    op.drop_table("attention_snapshots")
