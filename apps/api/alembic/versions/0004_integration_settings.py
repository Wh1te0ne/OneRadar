"""integration settings schema

Revision ID: 0004_integration_settings
Revises: 0003_folders_reading_states
Create Date: 2026-04-14 00:00:01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0004_integration_settings'
down_revision = '0003_folders_reading_states'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'integration_settings',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', sa.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('integration_key', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('config', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'integration_key', name='uq_integration_settings_user_key'),
    )
    op.create_index('ix_integration_settings_user_key', 'integration_settings', ['user_id', 'integration_key'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_integration_settings_user_key', table_name='integration_settings')
    op.drop_table('integration_settings')
