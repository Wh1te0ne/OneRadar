"""content artifacts schema

Revision ID: 0002_content_artifacts
Revises: 0001_initial_schema
Create Date: 2026-04-13 00:00:01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0002_content_artifacts'
down_revision = '0001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'content_snapshots',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('content_item_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('snapshot_type', sa.String(), nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=True),
        sa.Column('html_text', sa.Text(), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('content_hash', sa.String(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('source_headers', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('extra', sa.JSON(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_content_snapshots_item_fetched_at', 'content_snapshots', ['content_item_id', 'fetched_at'], unique=False)
    op.create_index('ix_content_snapshots_item_type_fetched_at', 'content_snapshots', ['content_item_id', 'snapshot_type', 'fetched_at'], unique=False)

    op.create_table(
        'content_parsed_documents',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('content_item_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parser_name', sa.String(), nullable=False),
        sa.Column('parser_version', sa.String(), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('byline', sa.Text(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('plain_text', sa.Text(), nullable=False),
        sa.Column('structured_blocks', sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('quality_score', sa.Float(), nullable=True),
        sa.Column('source_snapshot_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_snapshots.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('content_item_id', 'parser_name', 'parser_version', name='uq_content_parsed_documents_item_parser_version'),
    )
    op.create_index('ix_content_parsed_documents_item_created_at', 'content_parsed_documents', ['content_item_id', 'created_at'], unique=False)
    op.create_index('ix_content_parsed_documents_snapshot_id', 'content_parsed_documents', ['source_snapshot_id'], unique=False)

    op.create_table(
        'transcripts',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('content_item_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('transcript_type', sa.String(), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=True),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('segments', sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('source_snapshot_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_snapshots.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_transcripts_item_type_created_at', 'transcripts', ['content_item_id', 'transcript_type', 'created_at'], unique=False)
    op.create_index('ix_transcripts_snapshot_id', 'transcripts', ['source_snapshot_id'], unique=False)

    op.create_table(
        'summaries',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('content_item_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('summary_type', sa.String(), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=True),
        sa.Column('model_name', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source_parsed_document_id', sa.UUID(as_uuid=True), sa.ForeignKey('content_parsed_documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_transcript_id', sa.UUID(as_uuid=True), sa.ForeignKey('transcripts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('evidence', sa.JSON(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('content_item_id', 'summary_type', 'version', name='uq_summaries_item_type_version'),
    )
    op.create_index('ix_summaries_item_type_version', 'summaries', ['content_item_id', 'summary_type', 'version'], unique=False)
    op.create_index('ix_summaries_item_created_at', 'summaries', ['content_item_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_summaries_item_created_at', table_name='summaries')
    op.drop_index('ix_summaries_item_type_version', table_name='summaries')
    op.drop_table('summaries')

    op.drop_index('ix_transcripts_snapshot_id', table_name='transcripts')
    op.drop_index('ix_transcripts_item_type_created_at', table_name='transcripts')
    op.drop_table('transcripts')

    op.drop_index('ix_content_parsed_documents_snapshot_id', table_name='content_parsed_documents')
    op.drop_index('ix_content_parsed_documents_item_created_at', table_name='content_parsed_documents')
    op.drop_table('content_parsed_documents')

    op.drop_index('ix_content_snapshots_item_type_fetched_at', table_name='content_snapshots')
    op.drop_index('ix_content_snapshots_item_fetched_at', table_name='content_snapshots')
    op.drop_table('content_snapshots')
