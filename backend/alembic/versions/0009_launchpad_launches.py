"""launchpad_launches and chain_cursors: reading a curve off a chain.

The API-backed launchpad answers "what migrated recently" in one call. A chain
cannot, and the two halves of that fact arrive at different times and from
different places: a launch is a log entry, readable two thousand blocks at a
time on this node, and graduation is contract state that flips hours or days
later, one token per call.

So the launch gets written down and re-asked. `launchpad_launches.graduated` is
three-valued on purpose — true, false, and NULL for "nobody managed to ask",
which is what a rate-limited node, a reverting contract or an exhausted call
budget leaves behind. NULL is not "did not migrate", and the column exists so
the two can never be confused.

`chain_cursors` records how far the logs have been read. Without it a windowed
scan either re-reads the same blocks forever or steps over whatever happened
while the process was down — and the second failure is invisible, because
missing launches look exactly like a launchpad nobody uses.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "launchpad_launches",
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("address", sa.String(length=64), nullable=False),
        sa.Column("factory", sa.String(length=64), nullable=False),
        sa.Column("launched_at_block", sa.Integer(), nullable=False),
        sa.Column("graduated", sa.Boolean(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graduated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain", "address", name="uq_launches_chain_address"),
    )
    with op.batch_alter_table("launchpad_launches", schema=None) as batch:
        batch.create_index(batch.f("ix_launchpad_launches_chain"), ["chain"])
        batch.create_index(batch.f("ix_launchpad_launches_address"), ["address"])
        batch.create_index(batch.f("ix_launchpad_launches_is_demo"), ["is_demo"])

    op.create_table(
        "chain_cursors",
        sa.Column("chain", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("block", sa.Integer(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain", "name", name="uq_cursors_chain_name"),
    )
    with op.batch_alter_table("chain_cursors", schema=None) as batch:
        batch.create_index(batch.f("ix_chain_cursors_chain"), ["chain"])
        batch.create_index(batch.f("ix_chain_cursors_is_demo"), ["is_demo"])


def downgrade() -> None:
    op.drop_table("chain_cursors")
    op.drop_table("launchpad_launches")
