"""Remove the research built on positional horizons.

`build_dataset` used to slice the snapshot series by position:
`snapshots[index + horizon_hours]`. Measurements land on a quarter-hour grid,
so a template asking for six hours got six rows — ninety minutes — while the
hypothesis it fed said, in published text, "six hours later". The same applies
to the trailing window, and to the experiment `method` string, which stated the
horizon outright.

Every artefact produced that way makes a claim about a timescale that was never
measured. Correcting the code does not correct the rows, and there is nothing to
recompute them from: the statements were written for thresholds and outcomes the
new templates no longer use, so the honest move is to withdraw them and let the
cycle pose the questions again on its next run, in hours that are hours.

What is removed: hypotheses raised from the six original templates, the
experiments and results hanging off them, the patterns named after those
template keys, and the unpublished drafts derived from them. Nothing was
ever published to X — `X_MODE` is `draft` — so none of this leaves a public
record behind.

What is kept: `research_traces` (their hypothesis and experiment references are
`ON DELETE SET NULL`), observations, anomalies, snapshots, and memories. Those
record that the system ran and what it looked at, which is true and stays true.
The memories carry the old questions with their verdicts — mostly "no
measurement met the sample definition" — and deleting them would erase the
system's own record of having been wrong.

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

POSITIONAL_DATASET = "token-hours-v1"

RETIRED_TEMPLATES = {
    "volume-spike-survival",
    "withdrawal-death",
    "buy-pressure-reversal",
    "quiet-survivor",
    "concentration-withdrawal",
    "divergence-participation",
}


def _template_of(variables: object) -> str | None:
    """`variables` is JSON on Postgres and TEXT on SQLite. Read both."""
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except (TypeError, ValueError):
            return None
    if isinstance(variables, dict):
        key = variables.get("template")
        return key if isinstance(key, str) else None
    return None


def upgrade() -> None:
    connection = op.get_bind()

    hypothesis_ids = {
        row.hypothesis_id
        for row in connection.execute(
            sa.text(
                "SELECT DISTINCT hypothesis_id FROM experiments WHERE dataset_version = :version"
            ),
            {"version": POSITIONAL_DATASET},
        )
        if row.hypothesis_id
    }
    # Hypotheses that were raised but never tested carry the same wrong
    # timeframe, and no experiment row to find them by.
    hypothesis_ids.update(
        row.id
        for row in connection.execute(sa.text("SELECT id, variables FROM hypotheses"))
        if _template_of(row.variables) in RETIRED_TEMPLATES
    )

    if hypothesis_ids:
        ids = list(hypothesis_ids)
        experiment_ids = [
            row.id
            for row in connection.execute(
                sa.text("SELECT id FROM experiments WHERE hypothesis_id IN :ids").bindparams(
                    sa.bindparam("ids", value=ids, expanding=True)
                )
            )
        ]
        result_ids = (
            [
                row.id
                for row in connection.execute(
                    sa.text(
                        "SELECT id FROM experiment_results WHERE experiment_id IN :ids"
                    ).bindparams(sa.bindparam("ids", value=experiment_ids, expanding=True))
                )
            ]
            if experiment_ids
            else []
        )

        # Drafts reference their source by plain id, with no foreign key, so
        # they have to go before the cascade removes what they point at.
        orphaned = experiment_ids + result_ids + ids
        connection.execute(
            sa.text("DELETE FROM content_drafts WHERE source_id IN :ids").bindparams(
                sa.bindparam("ids", value=orphaned, expanding=True)
            )
        )
        # Deleted leaf first. `ON DELETE CASCADE` is declared on both foreign
        # keys, but SQLite only honours it with `PRAGMA foreign_keys` on, which
        # is off by default — a cascade that fires in production and leaves
        # orphans in every developer database is worse than no cascade.
        if result_ids:
            connection.execute(
                sa.text("DELETE FROM experiment_results WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", value=result_ids, expanding=True)
                )
            )
        if experiment_ids:
            connection.execute(
                sa.text("DELETE FROM experiments WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", value=experiment_ids, expanding=True)
                )
            )
        connection.execute(
            sa.text("DELETE FROM hypotheses WHERE id IN :ids").bindparams(
                sa.bindparam("ids", value=ids, expanding=True)
            )
        )

    connection.execute(
        sa.text("DELETE FROM patterns WHERE name IN :names").bindparams(
            sa.bindparam("names", value=sorted(RETIRED_TEMPLATES), expanding=True)
        )
    )


def downgrade() -> None:
    # Not reversible. The rows this removed described a horizon that was never
    # measured; restoring them would restore the false claim, and the data they
    # would need to be rebuilt correctly does not exist.
    pass
