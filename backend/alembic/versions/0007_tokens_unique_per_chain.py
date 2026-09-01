"""tokens: unique on the address *and* the chain, not the address alone.

The collector read one chain, so an address was a token. It reads more than one
now, and that assumption breaks in both directions:

- a legitimate token would be rejected because its address string already
  exists on another network, and
- worse, the lookup that goes with the constraint would find that other row and
  interleave two different assets' measurements into one series — silently, and
  in a way no later query could unpick.

No row is rewritten. Every existing token was measured on Solana and already
says so, so widening the key changes what is allowed next, not what is
recorded. `chain` is left exactly as collected.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tokens") as batch:
        batch.drop_constraint("uq_tokens_address", type_="unique")
        batch.create_unique_constraint("uq_tokens_address_chain", ["address", "chain"])


def downgrade() -> None:
    """Narrowing back can fail, and should.

    If two chains hold the same address by then, the old constraint has no
    honest way to keep both rows, and dropping one would delete measurements.
    Let the database refuse rather than choosing a row to lose.
    """
    with op.batch_alter_table("tokens") as batch:
        batch.drop_constraint("uq_tokens_address_chain", type_="unique")
        batch.create_unique_constraint("uq_tokens_address", ["address"])
