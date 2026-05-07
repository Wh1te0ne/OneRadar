"""daily news reports

Revision ID: 0008_daily_news_reports
Revises: 0007_rss_feed_state
Create Date: 2026-05-07 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '0008_daily_news_reports'
down_revision = '0007_rss_feed_state'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'daily_news_reports',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            'user_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('report_date', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ready'),
        sa.Column('headline', sa.Text(), nullable=False),
        sa.Column('lead', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('sections', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('source_entries', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('raw_model_output', sa.Text(), nullable=True),
        sa.Column('provider_name', sa.String(), nullable=True),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('entry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('freshness_hours', sa.Integer(), nullable=False, server_default='24'),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
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
        sa.UniqueConstraint('user_id', 'report_date', name='uq_daily_news_reports_user_date'),
    )
    op.create_index('ix_daily_news_reports_user_date', 'daily_news_reports', ['user_id', 'report_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_daily_news_reports_user_date', table_name='daily_news_reports')
    op.drop_table('daily_news_reports')
