"""memory: content hash and vector index

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25

Adds the dedupe key for stored memories and, on PostgreSQL, an HNSW index so
pgvector can rank by cosine distance without a sequential scan. SQLite keeps
the plain column: ranking there is a bounded Python pass.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VECTOR_INDEX = 'ix_memories_embedding_hnsw'


def upgrade() -> None:
    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_hash', sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_memories_content_hash'), ['content_hash'], unique=False
        )

    if op.get_bind().dialect.name == 'postgresql':
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {VECTOR_INDEX} '
            'ON memories USING hnsw (embedding vector_cosine_ops)'
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute(f'DROP INDEX IF EXISTS {VECTOR_INDEX}')

    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memories_content_hash'))
        batch_op.drop_column('content_hash')
