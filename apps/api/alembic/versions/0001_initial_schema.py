"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('username', sa.Text(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('username', name='uq_users_username'),
    )

    op.create_table(
        'content_items',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('source_platform', sa.String(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('normalized_url', sa.Text(), nullable=False),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('subtitle', sa.Text(), nullable=True),
        sa.Column('author_name', sa.String(), nullable=True),
        sa.Column('author_id', sa.String(), nullable=True),
        sa.Column('cover_url', sa.Text(), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('visibility', sa.String(), server_default=sa.text("'private'"), nullable=False),
        sa.Column('raw_meta', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('fetch_hash', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'normalized_url', name='uq_content_items_user_normalized_url'),
    )
    op.create_index('ix_content_items_user_status_imported_at', 'content_items', ['user_id', 'status', 'imported_at'], unique=False)
    op.create_index('ix_content_items_user_content_type_imported_at', 'content_items', ['user_id', 'content_type', 'imported_at'], unique=False)
    op.create_index('ix_content_items_user_source_platform_imported_at', 'content_items', ['user_id', 'source_platform', 'imported_at'], unique=False)

    op.create_table(
        'processing_tasks',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('content_item_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('priority', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default=sa.text('3'), nullable=False),
        sa.Column('locked_by', sa.String(), nullable=True),
        sa.Column('payload', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('result', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_processing_tasks_status_priority_created_at', 'processing_tasks', ['status', 'priority', 'created_at'], unique=False)
    op.create_index('ix_processing_tasks_item_task_created_at', 'processing_tasks', ['content_item_id', 'task_type', 'created_at'], unique=False)
    op.create_index('ix_processing_tasks_next_retry_at', 'processing_tasks', ['next_retry_at'], unique=False)

    op.create_table(
        'model_providers',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=False),
        sa.Column('provider_type', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('chat_model', sa.String(), nullable=True),
        sa.Column('embedding_model', sa.String(), nullable=True),
        sa.Column('transcription_model', sa.String(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('is_builtin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('config', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('last_test_status', sa.String(), nullable=True),
        sa.Column('last_tested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'provider_name', name='uq_model_providers_user_name'),
    )
    op.create_index('ix_model_providers_user_enabled_created_at', 'model_providers', ['user_id', 'is_enabled', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_model_providers_user_enabled_created_at', table_name='model_providers')
    op.drop_table('model_providers')

    op.drop_index('ix_processing_tasks_next_retry_at', table_name='processing_tasks')
    op.drop_index('ix_processing_tasks_item_task_created_at', table_name='processing_tasks')
    op.drop_index('ix_processing_tasks_status_priority_created_at', table_name='processing_tasks')
    op.drop_table('processing_tasks')

    op.drop_index('ix_content_items_user_source_platform_imported_at', table_name='content_items')
    op.drop_index('ix_content_items_user_content_type_imported_at', table_name='content_items')
    op.drop_index('ix_content_items_user_status_imported_at', table_name='content_items')
    op.drop_table('content_items')

    op.drop_table('users')
