from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = 'users'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    content_items: Mapped[list['ContentItem']] = relationship(back_populates='user')
    folders: Mapped[list['Folder']] = relationship(back_populates='user')
    reading_states: Mapped[list['ReadingState']] = relationship(back_populates='user')
    processing_tasks: Mapped[list['ProcessingTask']] = relationship(back_populates='user')
    model_providers: Mapped[list['ModelProvider']] = relationship(back_populates='user')
    integration_settings: Mapped[list['IntegrationSetting']] = relationship(back_populates='user')


class Folder(TimestampMixin, Base):
    __tablename__ = 'folders'
    __table_args__ = (
        UniqueConstraint('user_id', 'normalized_name', name='uq_folders_user_normalized_name'),
        Index('ix_folders_user_is_inbox_sort_order', 'user_id', 'is_inbox', 'sort_order'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    normalized_name: Mapped[str] = mapped_column(String, nullable=False)
    is_inbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User] = relationship(back_populates='folders')
    content_items: Mapped[list['ContentItem']] = relationship(back_populates='folder')



class IntegrationSetting(TimestampMixin, Base):
    __tablename__ = 'integration_settings'
    __table_args__ = (UniqueConstraint('user_id', 'integration_key', name='uq_integration_settings_user_key'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    integration_key: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    user: Mapped[User] = relationship(back_populates='integration_settings')


class ContentItem(TimestampMixin, Base):
    __tablename__ = 'content_items'
    __table_args__ = (
        UniqueConstraint('user_id', 'normalized_url', name='uq_content_items_user_normalized_url'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('folders.id', ondelete='SET NULL'), nullable=True
    )
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    source_platform: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    author_name: Mapped[str | None] = mapped_column(String, nullable=True)
    author_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    visibility: Mapped[str] = mapped_column(String, nullable=False, default='private')
    raw_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fetch_hash: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped[User] = relationship(back_populates='content_items')
    folder: Mapped[Folder | None] = relationship(back_populates='content_items')
    processing_tasks: Mapped[list['ProcessingTask']] = relationship(back_populates='content_item')
    content_snapshots: Mapped[list['ContentSnapshot']] = relationship(back_populates='content_item')
    content_parsed_documents: Mapped[list['ContentParsedDocument']] = relationship(back_populates='content_item')
    transcripts: Mapped[list['Transcript']] = relationship(back_populates='content_item')
    summaries: Mapped[list['Summary']] = relationship(back_populates='content_item')
    reading_state: Mapped['ReadingState | None'] = relationship(back_populates='content_item', uselist=False)


class ReadingState(TimestampMixin, Base):
    __tablename__ = 'reading_states'
    __table_args__ = (
        UniqueConstraint('user_id', 'content_item_id', name='uq_reading_states_user_item'),
        Index('ix_reading_states_user_is_read_last_read_at', 'user_id', 'is_read', 'last_read_at'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False
    )
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_position_type: Mapped[str | None] = mapped_column(String, nullable=True)
    last_position_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped[User] = relationship(back_populates='reading_states')
    content_item: Mapped[ContentItem] = relationship(back_populates='reading_state')


class ProcessingTask(TimestampMixin, Base):
    __tablename__ = 'processing_tasks'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    locked_by: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    content_item: Mapped[ContentItem] = relationship(back_populates='processing_tasks')
    user: Mapped[User] = relationship(back_populates='processing_tasks')


class ContentSnapshot(TimestampMixin, Base):
    __tablename__ = 'content_snapshots'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False
    )
    snapshot_type: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    html_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source_headers: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    content_item: Mapped[ContentItem] = relationship(back_populates='content_snapshots')


class ContentParsedDocument(TimestampMixin, Base):
    __tablename__ = 'content_parsed_documents'
    __table_args__ = (
        UniqueConstraint('content_item_id', 'parser_name', 'parser_version', name='uq_content_parsed_documents_item_parser_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False
    )
    parser_name: Mapped[str] = mapped_column(String, nullable=False)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    byline: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    plain_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_blocks: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_snapshots.id', ondelete='SET NULL'), nullable=True
    )

    content_item: Mapped[ContentItem] = relationship(back_populates='content_parsed_documents')


class Transcript(TimestampMixin, Base):
    __tablename__ = 'transcripts'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False
    )
    transcript_type: Mapped[str] = mapped_column(String, nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str | None] = mapped_column(String, nullable=True)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_snapshots.id', ondelete='SET NULL'), nullable=True
    )

    content_item: Mapped[ContentItem] = relationship(back_populates='transcripts')


class Summary(TimestampMixin, Base):
    __tablename__ = 'summaries'
    __table_args__ = (
        UniqueConstraint('content_item_id', 'summary_type', 'version', name='uq_summaries_item_type_version'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_items.id', ondelete='CASCADE'), nullable=False
    )
    summary_type: Mapped[str] = mapped_column(String, nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_parsed_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('content_parsed_documents.id', ondelete='SET NULL'), nullable=True
    )
    source_transcript_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey('transcripts.id', ondelete='SET NULL'), nullable=True
    )
    evidence: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)

    content_item: Mapped[ContentItem] = relationship(back_populates='summaries')


class ModelProvider(TimestampMixin, Base):
    __tablename__ = 'model_providers'
    __table_args__ = (UniqueConstraint('user_id', 'provider_name', name='uq_model_providers_user_name'),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String, nullable=False)
    provider_type: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    chat_model: Mapped[str | None] = mapped_column(String, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)
    transcription_model: Mapped[str | None] = mapped_column(String, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_test_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates='model_providers')
