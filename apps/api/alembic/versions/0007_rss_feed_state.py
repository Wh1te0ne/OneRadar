"""rss feed state schema

Revision ID: 0007_rss_feed_state
Revises: 0006_organization
Create Date: 2026-04-30 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0007_rss_feed_state'
down_revision = '0006_organization'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'feed_sources',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('site_title', sa.Text(), nullable=False),
        sa.Column('site_url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('last_loaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_refresh_status', sa.String(), nullable=True),
        sa.Column('last_refresh_error', sa.Text(), nullable=True),
        sa.Column('last_refreshed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.UniqueConstraint('user_id', 'source_url', name='uq_feed_sources_user_source_url'),
    )
    op.create_index('ix_feed_sources_user_last_loaded', 'feed_sources', ['user_id', 'last_loaded_at'], unique=False)

    op.create_table(
        'feed_entries',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'feed_source_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('feed_sources.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('entry_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('link', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('author', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('raw_item', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.UniqueConstraint('feed_source_id', 'entry_id', name='uq_feed_entries_source_entry_id'),
    )
    op.create_index('ix_feed_entries_user_published', 'feed_entries', ['user_id', 'published_at'], unique=False)
    op.create_index('ix_feed_entries_source_published', 'feed_entries', ['feed_source_id', 'published_at'], unique=False)

    op.create_table(
        'feed_entry_read_states',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'feed_entry_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('feed_entries.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('read_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.UniqueConstraint('user_id', 'feed_entry_id', name='uq_feed_entry_read_states_user_entry'),
    )
    op.create_index(
        'ix_feed_entry_read_states_user_read_at',
        'feed_entry_read_states',
        ['user_id', 'read_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_feed_entry_read_states_user_read_at', table_name='feed_entry_read_states')
    op.drop_table('feed_entry_read_states')
    op.drop_index('ix_feed_entries_source_published', table_name='feed_entries')
    op.drop_index('ix_feed_entries_user_published', table_name='feed_entries')
    op.drop_table('feed_entries')
    op.drop_index('ix_feed_sources_user_last_loaded', table_name='feed_sources')
    op.drop_table('feed_sources')
