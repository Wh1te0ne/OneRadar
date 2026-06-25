"""feed translation fields and refresh settings

Revision ID: 0013_feed_translation_and_refresh_settings
Revises: 0012_integration_tokens
Create Date: 2026-06-25 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_feed_translation_and_refresh_settings"
down_revision = "0012_integration_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feed_entries", sa.Column("translated_title", sa.Text(), nullable=True))
    op.add_column("feed_entries", sa.Column("translated_summary", sa.Text(), nullable=True))
    op.add_column("feed_entries", sa.Column("translation_language", sa.String(), nullable=True))
    op.add_column("feed_entries", sa.Column("translation_provider", sa.String(), nullable=True))
    op.add_column("feed_entries", sa.Column("translation_model", sa.String(), nullable=True))
    op.add_column("feed_entries", sa.Column("translation_status", sa.String(), nullable=True))
    op.add_column("feed_entries", sa.Column("translation_error", sa.Text(), nullable=True))
    op.add_column("feed_entries", sa.Column("translation_source_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "feed_entries",
        sa.Column("translated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_feed_entries_translation_status_published",
        "feed_entries",
        ["translation_status", "published_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feed_entries_translation_status_published", table_name="feed_entries")
    op.drop_column("feed_entries", "translated_at")
    op.drop_column("feed_entries", "translation_source_hash")
    op.drop_column("feed_entries", "translation_error")
    op.drop_column("feed_entries", "translation_status")
    op.drop_column("feed_entries", "translation_model")
    op.drop_column("feed_entries", "translation_provider")
    op.drop_column("feed_entries", "translation_language")
    op.drop_column("feed_entries", "translated_summary")
    op.drop_column("feed_entries", "translated_title")
