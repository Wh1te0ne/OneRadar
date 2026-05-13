"""integration tokens

Revision ID: 0012_integration_tokens
Revises: 0011_user_daily_news_share_key
Create Date: 2026-05-13 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0012_integration_tokens'
down_revision = '0011_user_daily_news_share_key'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'integration_tokens',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('token_prefix', sa.String(length=16), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_integration_tokens_token_hash'),
    )
    op.create_index(
        'ix_integration_tokens_user_created_at',
        'integration_tokens',
        ['user_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_integration_tokens_user_created_at', table_name='integration_tokens')
    op.drop_table('integration_tokens')
