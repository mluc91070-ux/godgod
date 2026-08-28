"""agents: how the job gets done, not just whether it is claimed.

`implemented` is a boolean and the roster needed three states. An agent whose
model calls are settled and one whose model calls run but are still being
watched are both "implemented", and collapsing them either overstates the new
ones or hides them. `stage` splits that: `model`, `beta`, `deterministic`.

This migration also **applies the roster**, which is unusual for a migration and
is deliberate. `seed_agents` only runs while `DEMO_MODE` is on, so a production
database is never reseeded: without this, the two agents that gained a model
would keep saying they had none, and the observer row would keep describing a
collector — its old entry claimed it produced `Observation` and `Anomaly` rows,
which the agent does not and must not do. Detection stays deterministic; the
agent reads an anomaly that already fired. Leaving that text in place would be
the roster lying about a capability, which is the one thing it exists to avoid.

The values here are the same ones in `data/fixtures/agents.json`. A database
that does get reseeded ends up in exactly this state anyway.

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.db.types import JSONDict

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ROSTER: dict[str, dict[str, object]] = {
    "writer": {"stage": "model", "implemented": True},
    "reviewer": {"stage": "model", "implemented": True},
    "critic": {
        "stage": "beta",
        "implemented": True,
        # "stricter only" is the whole guarantee. A roster that omitted it
        # would describe an agent that can overrule the deterministic checks.
        "outputs": ["critic verdict PASS | NEEDS_MORE_DATA | FAIL (stricter only)"],
    },
    "observer": {
        "stage": "beta",
        "implemented": True,
        "role": "Reads an anomaly the detectors already found",
        "question": "What does this measurement look like?",
        "inputs": ["Anomaly", "Observation payload", "detector thresholds"],
        "outputs": ["observation.payload.observer_reading"],
        "allowed_tools": ["db.read", "db.write:observations.payload"],
    },
    "researcher": {"stage": "deterministic", "implemented": False},
    "data_scientist": {"stage": "deterministic", "implemented": False},
}

# The list columns are JSONB on Postgres and JSON on SQLite. Borrowing the
# application's own type decorator is what makes one statement bind correctly
# on both, rather than hand-encoding and casting per dialect.
agents = sa.table(
    "agents",
    sa.column("name", sa.String),
    sa.column("stage", sa.String),
    sa.column("implemented", sa.Boolean),
    sa.column("role", sa.String),
    sa.column("question", sa.String),
    sa.column("inputs", JSONDict),
    sa.column("outputs", JSONDict),
    sa.column("allowed_tools", JSONDict),
)


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "stage",
            sa.String(length=16),
            nullable=False,
            server_default="deterministic",
        ),
    )
    for name, values in ROSTER.items():
        op.execute(agents.update().where(agents.c.name == name).values(**values))


def downgrade() -> None:
    # Only the column is reversible. The roster corrections describe what the
    # code does, and putting the old observer description back would restore a
    # claim that was never true.
    op.drop_column("agents", "stage")
