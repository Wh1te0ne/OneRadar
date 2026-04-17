# folders and reading states schema

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0003_folders_reading_states'
down_revision = '0002_content_artifacts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'folders',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('normalized_name', sa.String(), nullable=False),
        sa.Column('is_inbox', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('color', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'normalized_name', name='uq_folders_user_normalized_name'),
    )
    op.create_index('ix_folders_user_is_inbox_sort_order', 'folders', ['user_id', 'is_inbox', 'sort_order'], unique=False)

    op.add_column(
        'content_items',
        sa.Column('folder_id', sa.UUID(as_uuid=True), sa.ForeignKey('folders.id', ondelete='SET NULL'), nullable=True),
    )
    op.create_index('ix_content_items_folder_id', 'content_items', ['folder_id'], unique=False)

    op.create_table(
        'reading_states',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content_item_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('progress_percent', sa.Float(), server_default=sa.text('0.0'), nullable=False),
        sa.Column('last_position_type', sa.String(), nullable=True),
        sa.Column('last_position_value', sa.Text(), nullable=True),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_archived', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'content_item_id', name='uq_reading_states_user_item'),
    )
    op.create_index('ix_reading_states_user_is_read_last_read_at', 'reading_states', ['user_id', 'is_read', 'last_read_at'], unique=False)

    conn = op.get_bind()
    user_ids = [row[0] for row in conn.execute(sa.text('SELECT id FROM users')).fetchall()]
    for user_id in user_ids:
        folder_id = uuid.uuid4()
        conn.execute(
            sa.text(
                'INSERT INTO folders (id, user_id, name, normalized_name, is_inbox, sort_order, color, created_at, updated_at) '
                'VALUES (:id, :user_id, :name, :normalized_name, :is_inbox, :sort_order, :color, now(), now())'
            ),
            {
                'id': folder_id,
                'user_id': user_id,
                'name': 'Inbox',
                'normalized_name': 'inbox',
                'is_inbox': True,
                'sort_order': 0,
                'color': None,
            },
        )
        conn.execute(
            sa.text('UPDATE content_items SET folder_id = :folder_id WHERE user_id = :user_id AND folder_id IS NULL'),
            {'folder_id': folder_id, 'user_id': user_id},
        )


def downgrade() -> None:
    op.drop_index('ix_reading_states_user_is_read_last_read_at', table_name='reading_states')
    op.drop_table('reading_states')

    op.drop_index('ix_content_items_folder_id', table_name='content_items')
    op.drop_column('content_items', 'folder_id')

    op.drop_index('ix_folders_user_is_inbox_sort_order', table_name='folders')
    op.drop_table('folders')
