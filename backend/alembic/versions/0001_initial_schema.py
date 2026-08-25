"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-25

Creates every PHASE 1 table. On PostgreSQL the pgvector extension is
enabled first so the memories.embedding column can be created as a real
``vector`` — on SQLite the same column degrades to TEXT (see app/db/types.py).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

import app.db.types


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    op.create_table('agents',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('role', sa.String(length=256), nullable=False),
    sa.Column('question', sa.String(length=256), nullable=False),
    sa.Column('inputs', app.db.types.JSONDict(), nullable=True),
    sa.Column('outputs', app.db.types.JSONDict(), nullable=True),
    sa.Column('allowed_tools', app.db.types.JSONDict(), nullable=True),
    sa.Column('model_role', sa.String(length=32), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('implemented', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agents_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_agents_name'), ['name'], unique=True)

    op.create_table('content_drafts',
    sa.Column('content_type', sa.String(length=32), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('reviewer_verdict', sa.String(length=32), nullable=True),
    sa.Column('reviewer_notes', sa.Text(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('source_kind', sa.String(length=32), nullable=True),
    sa.Column('source_id', sa.String(length=36), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approved_by', sa.String(length=128), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('content_drafts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_content_drafts_content_type'), ['content_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_content_drafts_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_content_drafts_source_id'), ['source_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_content_drafts_status'), ['status'], unique=False)

    op.create_table('memories',
    sa.Column('memory_type', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('meta', app.db.types.JSONDict(), nullable=True),
    sa.Column('source', sa.String(length=256), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('ref_type', sa.String(length=32), nullable=True),
    sa.Column('ref_id', sa.String(length=36), nullable=True),
    sa.Column('embedding', app.db.types.Embedding(), nullable=True),
    sa.Column('embedding_model', sa.String(length=128), nullable=True),
    sa.Column('access_count', sa.Integer(), nullable=False),
    sa.Column('last_accessed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_memories_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_memories_memory_type'), ['memory_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_memories_ref_id'), ['ref_id'], unique=False)

    op.create_table('metrics_snapshots',
    sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('window', sa.String(length=16), nullable=False),
    sa.Column('observations_count', sa.Integer(), nullable=True),
    sa.Column('anomalies_count', sa.Integer(), nullable=True),
    sa.Column('hypotheses_count', sa.Integer(), nullable=True),
    sa.Column('experiments_count', sa.Integer(), nullable=True),
    sa.Column('supported_count', sa.Integer(), nullable=True),
    sa.Column('rejected_count', sa.Integer(), nullable=True),
    sa.Column('inconclusive_count', sa.Integer(), nullable=True),
    sa.Column('memories_count', sa.Integer(), nullable=True),
    sa.Column('llm_cost_usd', sa.Float(), nullable=True),
    sa.Column('detail', app.db.types.JSONDict(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('metrics_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_metrics_snapshots_captured_at'), ['captured_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_metrics_snapshots_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_metrics_snapshots_window'), ['window'], unique=False)

    op.create_table('observations',
    sa.Column('seq', sa.Integer(), nullable=True),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('subject_type', sa.String(length=32), nullable=True),
    sa.Column('subject_ref', sa.String(length=128), nullable=True),
    sa.Column('payload', app.db.types.JSONDict(), nullable=True),
    sa.Column('novelty_score', sa.Float(), nullable=True),
    sa.Column('importance', sa.Float(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('source', sa.String(length=128), nullable=True),
    sa.Column('llm_reviewed', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('observations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_observations_importance'), ['importance'], unique=False)
        batch_op.create_index(batch_op.f('ix_observations_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_observations_kind'), ['kind'], unique=False)
        batch_op.create_index(batch_op.f('ix_observations_novelty_score'), ['novelty_score'], unique=False)
        batch_op.create_index(batch_op.f('ix_observations_observed_at'), ['observed_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_observations_seq'), ['seq'], unique=False)
        batch_op.create_index(batch_op.f('ix_observations_subject_ref'), ['subject_ref'], unique=False)

    op.create_table('patterns',
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('support_count', sa.Integer(), nullable=False),
    sa.Column('contradiction_count', sa.Integer(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('evidence_refs', app.db.types.JSONDict(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('patterns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_patterns_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_patterns_status'), ['status'], unique=False)

    op.create_table('research_sources',
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('url', sa.String(length=512), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('reliability', sa.Float(), nullable=True),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('research_sources', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_research_sources_is_demo'), ['is_demo'], unique=False)

    op.create_table('social_accounts',
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=False),
    sa.Column('handle', sa.String(length=128), nullable=True),
    sa.Column('display_name', sa.String(length=256), nullable=True),
    sa.Column('followers', sa.Integer(), nullable=True),
    sa.Column('account_created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('raw_metadata', app.db.types.JSONDict(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('platform', 'external_id', name='uq_social_account')
    )
    with op.batch_alter_table('social_accounts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_social_accounts_external_id'), ['external_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_social_accounts_handle'), ['handle'], unique=False)
        batch_op.create_index(batch_op.f('ix_social_accounts_is_demo'), ['is_demo'], unique=False)

    op.create_table('system_events',
    sa.Column('seq', sa.Integer(), nullable=True),
    sa.Column('event_type', sa.String(length=48), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('ref_type', sa.String(length=32), nullable=True),
    sa.Column('ref_id', sa.String(length=36), nullable=True),
    sa.Column('detail', app.db.types.JSONDict(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('system_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_system_events_event_type'), ['event_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_events_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_events_occurred_at'), ['occurred_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_events_ref_id'), ['ref_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_system_events_seq'), ['seq'], unique=False)

    op.create_table('tokens',
    sa.Column('address', sa.String(length=64), nullable=False),
    sa.Column('chain', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=256), nullable=True),
    sa.Column('symbol', sa.String(length=64), nullable=True),
    sa.Column('decimals', sa.Integer(), nullable=True),
    sa.Column('launch_time', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bonding_curve_state', sa.String(length=64), nullable=True),
    sa.Column('migrated_to_dex', sa.String(length=64), nullable=True),
    sa.Column('launchpad', sa.String(length=64), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('market_cap_usd', sa.Float(), nullable=True),
    sa.Column('liquidity_usd', sa.Float(), nullable=True),
    sa.Column('volume_24h_usd', sa.Float(), nullable=True),
    sa.Column('holders', sa.Integer(), nullable=True),
    sa.Column('holder_concentration_top10', sa.Float(), nullable=True),
    sa.Column('source', sa.String(length=128), nullable=True),
    sa.Column('raw_metadata', app.db.types.JSONDict(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('address', name='uq_tokens_address')
    )
    with op.batch_alter_table('tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tokens_address'), ['address'], unique=False)
        batch_op.create_index(batch_op.f('ix_tokens_is_demo'), ['is_demo'], unique=False)

    op.create_table('wallet_clusters',
    sa.Column('label', sa.String(length=256), nullable=True),
    sa.Column('method', sa.String(length=128), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('size', sa.Integer(), nullable=True),
    sa.Column('evidence', app.db.types.JSONDict(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('wallet_clusters', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wallet_clusters_is_demo'), ['is_demo'], unique=False)

    op.create_table('agent_runs',
    sa.Column('agent_id', sa.String(length=36), nullable=True),
    sa.Column('agent_name', sa.String(length=64), nullable=False),
    sa.Column('model', sa.String(length=128), nullable=True),
    sa.Column('input_summary', sa.Text(), nullable=True),
    sa.Column('output_summary', sa.Text(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('estimated_cost_usd', sa.Float(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['agent_id'], ['agents.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_runs_agent_id'), ['agent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_agent_name'), ['agent_name'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_started_at'), ['started_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_runs_status'), ['status'], unique=False)

    op.create_table('anomalies',
    sa.Column('observation_id', sa.String(length=36), nullable=True),
    sa.Column('anomaly_type', sa.String(length=64), nullable=False),
    sa.Column('detector', sa.String(length=128), nullable=False),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('baseline', app.db.types.JSONDict(), nullable=True),
    sa.Column('measured', app.db.types.JSONDict(), nullable=True),
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['observation_id'], ['observations.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_anomalies_anomaly_type'), ['anomaly_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_detected_at'), ['detected_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_observation_id'), ['observation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_anomalies_score'), ['score'], unique=False)

    op.create_table('hypotheses',
    sa.Column('seq', sa.Integer(), nullable=True),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('variables', app.db.types.JSONDict(), nullable=True),
    sa.Column('population', sa.Text(), nullable=False),
    sa.Column('sample_definition', sa.Text(), nullable=False),
    sa.Column('timeframe', sa.String(length=256), nullable=False),
    sa.Column('baseline', sa.Text(), nullable=False),
    sa.Column('expected_result', sa.Text(), nullable=False),
    sa.Column('falsification_condition', sa.Text(), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('origin_observation_id', sa.String(length=36), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['origin_observation_id'], ['observations.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('hypotheses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_hypotheses_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_hypotheses_origin_observation_id'), ['origin_observation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_hypotheses_seq'), ['seq'], unique=False)
        batch_op.create_index(batch_op.f('ix_hypotheses_status'), ['status'], unique=False)

    op.create_table('published_posts',
    sa.Column('draft_id', sa.String(length=36), nullable=False),
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=True),
    sa.Column('url', sa.String(length=512), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('engagement', app.db.types.JSONDict(), nullable=True),
    sa.Column('engagement_checked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reach_score', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['draft_id'], ['content_drafts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('published_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_published_posts_draft_id'), ['draft_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_published_posts_is_demo'), ['is_demo'], unique=False)

    op.create_table('social_posts',
    sa.Column('platform', sa.String(length=32), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=True),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('lang', sa.String(length=16), nullable=True),
    sa.Column('likes', sa.Integer(), nullable=True),
    sa.Column('reposts', sa.Integer(), nullable=True),
    sa.Column('replies', sa.Integer(), nullable=True),
    sa.Column('matched_terms', app.db.types.JSONDict(), nullable=True),
    sa.Column('mentions_token_address', sa.String(length=64), nullable=True),
    sa.Column('source', sa.String(length=128), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['social_accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('platform', 'external_id', name='uq_social_post')
    )
    with op.batch_alter_table('social_posts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_social_posts_account_id'), ['account_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_social_posts_external_id'), ['external_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_social_posts_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_social_posts_mentions_token_address'), ['mentions_token_address'], unique=False)
        batch_op.create_index(batch_op.f('ix_social_posts_posted_at'), ['posted_at'], unique=False)

    op.create_table('token_snapshots',
    sa.Column('token_id', sa.String(length=36), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('market_cap_usd', sa.Float(), nullable=True),
    sa.Column('liquidity_usd', sa.Float(), nullable=True),
    sa.Column('volume_usd', sa.Float(), nullable=True),
    sa.Column('holders', sa.Integer(), nullable=True),
    sa.Column('holder_concentration_top10', sa.Float(), nullable=True),
    sa.Column('transactions', sa.Integer(), nullable=True),
    sa.Column('buys', sa.Integer(), nullable=True),
    sa.Column('sells', sa.Integer(), nullable=True),
    sa.Column('age_seconds', sa.Integer(), nullable=True),
    sa.Column('liquidity_change_pct', sa.Float(), nullable=True),
    sa.Column('holder_change_pct', sa.Float(), nullable=True),
    sa.Column('source', sa.String(length=128), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['token_id'], ['tokens.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('token_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_token_snapshots_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_token_snapshots_observed_at'), ['observed_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_token_snapshots_token_id'), ['token_id'], unique=False)

    op.create_table('wallets',
    sa.Column('address', sa.String(length=64), nullable=False),
    sa.Column('chain', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=256), nullable=True),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('cluster_id', sa.String(length=36), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['cluster_id'], ['wallet_clusters.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('address', name='uq_wallets_address')
    )
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wallets_address'), ['address'], unique=False)
        batch_op.create_index(batch_op.f('ix_wallets_cluster_id'), ['cluster_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wallets_is_demo'), ['is_demo'], unique=False)

    op.create_table('experiments',
    sa.Column('seq', sa.Integer(), nullable=True),
    sa.Column('hypothesis_id', sa.String(length=36), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=False),
    sa.Column('method', sa.Text(), nullable=False),
    sa.Column('features', app.db.types.JSONDict(), nullable=True),
    sa.Column('parameters', app.db.types.JSONDict(), nullable=True),
    sa.Column('dataset_version', sa.String(length=64), nullable=False),
    sa.Column('dataset_hash', sa.String(length=128), nullable=False),
    sa.Column('sample_size', sa.Integer(), nullable=True),
    sa.Column('train_period', sa.String(length=128), nullable=True),
    sa.Column('validation_period', sa.String(length=128), nullable=True),
    sa.Column('out_of_sample_period', sa.String(length=128), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('limitations', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['hypothesis_id'], ['hypotheses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('experiments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_experiments_hypothesis_id'), ['hypothesis_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_experiments_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_experiments_seq'), ['seq'], unique=False)
        batch_op.create_index(batch_op.f('ix_experiments_status'), ['status'], unique=False)

    op.create_table('experiment_results',
    sa.Column('experiment_id', sa.String(length=36), nullable=False),
    sa.Column('outcome', sa.String(length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('metrics', app.db.types.JSONDict(), nullable=True),
    sa.Column('effect_size', sa.Float(), nullable=True),
    sa.Column('p_value', sa.Float(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('critic_verdict', sa.String(length=32), nullable=True),
    sa.Column('critic_notes', sa.Text(), nullable=True),
    sa.Column('critic_checks', app.db.types.JSONDict(), nullable=True),
    sa.Column('limitations', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('experiment_results', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_experiment_results_critic_verdict'), ['critic_verdict'], unique=False)
        batch_op.create_index(batch_op.f('ix_experiment_results_experiment_id'), ['experiment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_experiment_results_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_experiment_results_outcome'), ['outcome'], unique=False)

    op.create_table('research_traces',
    sa.Column('seq', sa.Integer(), nullable=True),
    sa.Column('title', sa.String(length=512), nullable=True),
    sa.Column('hypothesis_id', sa.String(length=36), nullable=True),
    sa.Column('experiment_id', sa.String(length=36), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['experiment_id'], ['experiments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['hypothesis_id'], ['hypotheses.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('research_traces', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_research_traces_experiment_id'), ['experiment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_research_traces_hypothesis_id'), ['hypothesis_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_research_traces_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_research_traces_seq'), ['seq'], unique=False)

    op.create_table('trace_steps',
    sa.Column('trace_id', sa.String(length=36), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('ref_type', sa.String(length=32), nullable=True),
    sa.Column('ref_id', sa.String(length=36), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('detail', app.db.types.JSONDict(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['trace_id'], ['research_traces.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('trace_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_trace_steps_is_demo'), ['is_demo'], unique=False)
        batch_op.create_index(batch_op.f('ix_trace_steps_trace_id'), ['trace_id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('trace_steps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_trace_steps_trace_id'))
        batch_op.drop_index(batch_op.f('ix_trace_steps_is_demo'))

    op.drop_table('trace_steps')
    with op.batch_alter_table('research_traces', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_research_traces_seq'))
        batch_op.drop_index(batch_op.f('ix_research_traces_is_demo'))
        batch_op.drop_index(batch_op.f('ix_research_traces_hypothesis_id'))
        batch_op.drop_index(batch_op.f('ix_research_traces_experiment_id'))

    op.drop_table('research_traces')
    with op.batch_alter_table('experiment_results', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_experiment_results_outcome'))
        batch_op.drop_index(batch_op.f('ix_experiment_results_is_demo'))
        batch_op.drop_index(batch_op.f('ix_experiment_results_experiment_id'))
        batch_op.drop_index(batch_op.f('ix_experiment_results_critic_verdict'))

    op.drop_table('experiment_results')
    with op.batch_alter_table('experiments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_experiments_status'))
        batch_op.drop_index(batch_op.f('ix_experiments_seq'))
        batch_op.drop_index(batch_op.f('ix_experiments_is_demo'))
        batch_op.drop_index(batch_op.f('ix_experiments_hypothesis_id'))

    op.drop_table('experiments')
    with op.batch_alter_table('wallets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wallets_is_demo'))
        batch_op.drop_index(batch_op.f('ix_wallets_cluster_id'))
        batch_op.drop_index(batch_op.f('ix_wallets_address'))

    op.drop_table('wallets')
    with op.batch_alter_table('token_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_token_snapshots_token_id'))
        batch_op.drop_index(batch_op.f('ix_token_snapshots_observed_at'))
        batch_op.drop_index(batch_op.f('ix_token_snapshots_is_demo'))

    op.drop_table('token_snapshots')
    with op.batch_alter_table('social_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_social_posts_posted_at'))
        batch_op.drop_index(batch_op.f('ix_social_posts_mentions_token_address'))
        batch_op.drop_index(batch_op.f('ix_social_posts_is_demo'))
        batch_op.drop_index(batch_op.f('ix_social_posts_external_id'))
        batch_op.drop_index(batch_op.f('ix_social_posts_account_id'))

    op.drop_table('social_posts')
    with op.batch_alter_table('published_posts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_published_posts_is_demo'))
        batch_op.drop_index(batch_op.f('ix_published_posts_draft_id'))

    op.drop_table('published_posts')
    with op.batch_alter_table('hypotheses', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_hypotheses_status'))
        batch_op.drop_index(batch_op.f('ix_hypotheses_seq'))
        batch_op.drop_index(batch_op.f('ix_hypotheses_origin_observation_id'))
        batch_op.drop_index(batch_op.f('ix_hypotheses_is_demo'))

    op.drop_table('hypotheses')
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_anomalies_score'))
        batch_op.drop_index(batch_op.f('ix_anomalies_observation_id'))
        batch_op.drop_index(batch_op.f('ix_anomalies_is_demo'))
        batch_op.drop_index(batch_op.f('ix_anomalies_detected_at'))
        batch_op.drop_index(batch_op.f('ix_anomalies_anomaly_type'))

    op.drop_table('anomalies')
    with op.batch_alter_table('agent_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agent_runs_status'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_started_at'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_is_demo'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_agent_name'))
        batch_op.drop_index(batch_op.f('ix_agent_runs_agent_id'))

    op.drop_table('agent_runs')
    with op.batch_alter_table('wallet_clusters', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wallet_clusters_is_demo'))

    op.drop_table('wallet_clusters')
    with op.batch_alter_table('tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tokens_is_demo'))
        batch_op.drop_index(batch_op.f('ix_tokens_address'))

    op.drop_table('tokens')
    with op.batch_alter_table('system_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_system_events_seq'))
        batch_op.drop_index(batch_op.f('ix_system_events_ref_id'))
        batch_op.drop_index(batch_op.f('ix_system_events_occurred_at'))
        batch_op.drop_index(batch_op.f('ix_system_events_is_demo'))
        batch_op.drop_index(batch_op.f('ix_system_events_event_type'))

    op.drop_table('system_events')
    with op.batch_alter_table('social_accounts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_social_accounts_is_demo'))
        batch_op.drop_index(batch_op.f('ix_social_accounts_handle'))
        batch_op.drop_index(batch_op.f('ix_social_accounts_external_id'))

    op.drop_table('social_accounts')
    with op.batch_alter_table('research_sources', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_research_sources_is_demo'))

    op.drop_table('research_sources')
    with op.batch_alter_table('patterns', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_patterns_status'))
        batch_op.drop_index(batch_op.f('ix_patterns_is_demo'))

    op.drop_table('patterns')
    with op.batch_alter_table('observations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_observations_subject_ref'))
        batch_op.drop_index(batch_op.f('ix_observations_seq'))
        batch_op.drop_index(batch_op.f('ix_observations_observed_at'))
        batch_op.drop_index(batch_op.f('ix_observations_novelty_score'))
        batch_op.drop_index(batch_op.f('ix_observations_kind'))
        batch_op.drop_index(batch_op.f('ix_observations_is_demo'))
        batch_op.drop_index(batch_op.f('ix_observations_importance'))

    op.drop_table('observations')
    with op.batch_alter_table('metrics_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_metrics_snapshots_window'))
        batch_op.drop_index(batch_op.f('ix_metrics_snapshots_is_demo'))
        batch_op.drop_index(batch_op.f('ix_metrics_snapshots_captured_at'))

    op.drop_table('metrics_snapshots')
    with op.batch_alter_table('memories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_memories_ref_id'))
        batch_op.drop_index(batch_op.f('ix_memories_memory_type'))
        batch_op.drop_index(batch_op.f('ix_memories_is_demo'))

    op.drop_table('memories')
    with op.batch_alter_table('content_drafts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_content_drafts_status'))
        batch_op.drop_index(batch_op.f('ix_content_drafts_source_id'))
        batch_op.drop_index(batch_op.f('ix_content_drafts_is_demo'))
        batch_op.drop_index(batch_op.f('ix_content_drafts_content_type'))

    op.drop_table('content_drafts')
    with op.batch_alter_table('agents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_agents_name'))
        batch_op.drop_index(batch_op.f('ix_agents_is_demo'))

    op.drop_table('agents')
    # ### end Alembic commands ###
