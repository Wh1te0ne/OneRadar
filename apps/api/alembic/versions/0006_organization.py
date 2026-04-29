"""tags and collections schema

Revision ID: 0006_organization
Revises: 0005_annotations
Create Date: 2026-04-28 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0006_organization'
down_revision = '0005_annotations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tags',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('normalized_name', sa.Text(), nullable=False),
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
        sa.UniqueConstraint('user_id', 'normalized_name', name='uq_tags_user_normalized_name'),
    )
    op.create_index('ix_tags_user_name', 'tags', ['user_id', 'name'], unique=False)

    op.create_table(
        'collections',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), server_default=sa.text('false'), nullable=False),
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
        sa.UniqueConstraint('user_id', 'name', name='uq_collections_user_name'),
    )
    op.create_index(
        'ix_collections_user_favorite_created',
        'collections',
        ['user_id', 'is_favorite', 'created_at'],
        unique=False,
    )

    op.create_table(
        'content_item_tags',
        sa.Column(
            'content_item_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('content_items.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'tag_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('tags.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('score', sa.Float(), nullable=True),
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
        sa.PrimaryKeyConstraint('content_item_id', 'tag_id', name='pk_content_item_tags'),
    )
    op.create_index(
        'ix_content_item_tags_tag_item',
        'content_item_tags',
        ['tag_id', 'content_item_id'],
        unique=False,
    )

    op.create_table(
        'collection_items',
        sa.Column(
            'collection_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('collections.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'content_item_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('content_items.id', ondelete='CASCADE'),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint('collection_id', 'content_item_id', name='pk_collection_items'),
    )
    op.create_index(
        'ix_collection_items_item_collection',
        'collection_items',
        ['content_item_id', 'collection_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_collection_items_item_collection', table_name='collection_items')
    op.drop_table('collection_items')
    op.drop_index('ix_content_item_tags_tag_item', table_name='content_item_tags')
    op.drop_table('content_item_tags')
    op.drop_index('ix_collections_user_favorite_created', table_name='collections')
    op.drop_table('collections')
    op.drop_index('ix_tags_user_name', table_name='tags')
    op.drop_table('tags')
