"""annotation schema

Revision ID: 0005_annotations
Revises: 0004_integration_settings
Create Date: 2026-04-28 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0005_annotations'
down_revision = '0004_integration_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'highlights',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'content_item_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('content_items.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('anchor_type', sa.String(), nullable=False),
        sa.Column('quote_text', sa.Text(), nullable=False),
        sa.Column('start_anchor', sa.Text(), nullable=True),
        sa.Column('end_anchor', sa.Text(), nullable=True),
        sa.Column('start_offset', sa.Integer(), nullable=True),
        sa.Column('end_offset', sa.Integer(), nullable=True),
        sa.Column('segment_index', sa.Integer(), nullable=True),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('note_id', sa.UUID(as_uuid=True), nullable=True),
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
    )
    op.create_table(
        'notes',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'content_item_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('content_items.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'highlight_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('highlights.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('content', sa.Text(), nullable=False),
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
    )
    op.create_foreign_key(
        'fk_highlights_note_id_notes',
        'highlights',
        'notes',
        ['note_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_highlights_user_item_created_at',
        'highlights',
        ['user_id', 'content_item_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_highlights_item_created_at',
        'highlights',
        ['content_item_id', 'created_at'],
        unique=False,
    )
    op.create_index('ix_highlights_note_id', 'highlights', ['note_id'], unique=False)
    op.create_index(
        'ix_notes_user_item_created_at',
        'notes',
        ['user_id', 'content_item_id', 'created_at'],
        unique=False,
    )
    op.create_index('ix_notes_highlight_id', 'notes', ['highlight_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notes_highlight_id', table_name='notes')
    op.drop_index('ix_notes_user_item_created_at', table_name='notes')
    op.drop_index('ix_highlights_note_id', table_name='highlights')
    op.drop_index('ix_highlights_item_created_at', table_name='highlights')
    op.drop_index('ix_highlights_user_item_created_at', table_name='highlights')
    op.drop_constraint('fk_highlights_note_id_notes', 'highlights', type_='foreignkey')
    op.drop_table('notes')
    op.drop_table('highlights')
