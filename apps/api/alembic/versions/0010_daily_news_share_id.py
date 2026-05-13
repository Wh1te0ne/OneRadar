"""daily news share id

Revision ID: 0010_daily_news_share_id
Revises: 0009_user_email_auth_bootstrap
Create Date: 2026-05-12 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0010_daily_news_share_id'
down_revision = '0009_user_email_auth_bootstrap'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('daily_news_reports', sa.Column('share_id', sa.String(length=48), nullable=True))
    op.create_index('ix_daily_news_reports_share_id', 'daily_news_reports', ['share_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_daily_news_reports_share_id', table_name='daily_news_reports')
    op.drop_column('daily_news_reports', 'share_id')
