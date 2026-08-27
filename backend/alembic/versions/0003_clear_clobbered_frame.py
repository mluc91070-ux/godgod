"""tokens: erase the sampling frame the observation pipeline overwrote

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-27

`ObservationPipeline._upsert_token` assigned every field on every run,
including `Token.source`. That was harmless while fixtures were the only thing
that created tokens, and became silent data loss once the pipeline started
running live every quarter hour: it read the collector's own tokens back
through `DatabaseObservationSource` and stamped `source = 'database-live'` over
the frame that recorded whether a token came from the promotion feed or from a
completed bonding curve. Measured on production before this ran: 144 of 144
live tokens.

`'database-live'` is never a real frame. The live source only ever lists tokens
that already exist, so it creates none and can legitimately name none; every
row carrying that value got it from the bug. It is set to NULL rather than
guessed at, because which feed found a given token months ago is not
recoverable from anything still stored — and a guessed frame would silently
mis-stratify every experiment that reads it, which is the exact failure this
column exists to prevent. `/api/status` counts these as
`tokens_unrecorded_frame` and says so on the page.

Tokens collected after the fix record their frame at creation, as they always
should have.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLOBBERED = 'database-live'


def upgrade() -> None:
    tokens = sa.table('tokens', sa.column('source', sa.String))
    op.execute(
        tokens.update().where(tokens.c.source == CLOBBERED).values(source=None)
    )


def downgrade() -> None:
    # Not reversible: the values this removed were wrong, and the ones they
    # replaced were destroyed by the bug, not by this migration.
    pass
