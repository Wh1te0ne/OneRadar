"""user daily news share key

Revision ID: 0011_user_daily_news_share_key
Revises: 0010_daily_news_share_id
Create Date: 2026-05-12 00:00:02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0011_user_daily_news_share_key'
down_revision = '0010_daily_news_share_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('daily_news_share_key', sa.String(length=48), nullable=True))
    op.create_index('ix_users_daily_news_share_key', 'users', ['daily_news_share_key'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_daily_news_share_key', table_name='users')
    op.drop_column('users', 'daily_news_share_key')
