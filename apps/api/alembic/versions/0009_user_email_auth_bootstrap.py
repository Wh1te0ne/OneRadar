"""user email auth bootstrap

Revision ID: 0009_user_email_auth_bootstrap
Revises: 0008_daily_news_reports
Create Date: 2026-05-12 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = '0009_user_email_auth_bootstrap'
down_revision = '0008_daily_news_reports'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(), nullable=True))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.execute("UPDATE users SET username = 'whiteone', display_name = COALESCE(display_name, 'whiteone') WHERE username = 'local'")


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.drop_column('users', 'email')
