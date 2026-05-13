from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    create_engine,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.engine import Engine

from .credential_crypto import reveal_secret

PENDING_STATUS = 'pending'
RUNNING_STATUS = 'running'
RETRYING_STATUS = 'retrying'
SUCCESS_STATUS = 'success'
FAILED_STATUS = 'failed'
CANCELED_STATUS = 'canceled'
SUPPORTED_TASK_TYPES = {'fetch_meta', 'reprocess_item', 'generate_summary'}

metadata = MetaData()

processing_tasks = Table(
    'processing_tasks',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('content_item_id', Uuid, nullable=False),
    Column('user_id', Uuid, nullable=False),
    Column('task_type', String, nullable=False),
    Column('status', String, nullable=False),
    Column('priority', Integer, nullable=False),
    Column('attempt_count', Integer, nullable=False),
    Column('max_attempts', Integer, nullable=False),
    Column('locked_by', String, nullable=True),
    Column('payload', JSON, nullable=False),
    Column('result', JSON, nullable=False),
    Column('error_message', Text, nullable=True),
    Column('started_at', DateTime(timezone=True), nullable=True),
    Column('finished_at', DateTime(timezone=True), nullable=True),
    Column('next_retry_at', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

integration_settings = Table(
    'integration_settings',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('user_id', Uuid, nullable=False),
    Column('integration_key', String, nullable=False),
    Column('display_name', String, nullable=False),
    Column('is_enabled', Boolean, nullable=False),
    Column('config', JSON, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

model_providers = Table(
    'model_providers',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('user_id', Uuid, nullable=False),
    Column('provider_name', String, nullable=False),
    Column('provider_type', String, nullable=False),
    Column('display_name', String, nullable=False),
    Column('base_url', Text, nullable=True),
    Column('api_key_encrypted', Text, nullable=True),
    Column('chat_model', String, nullable=True),
    Column('embedding_model', String, nullable=True),
    Column('transcription_model', String, nullable=True),
    Column('is_enabled', Boolean, nullable=False),
    Column('is_builtin', Boolean, nullable=False),
    Column('config', JSON, nullable=False),
    Column('last_test_status', String, nullable=True),
    Column('last_tested_at', DateTime(timezone=True), nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

content_items = Table(
    'content_items',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('user_id', Uuid, nullable=False),
    Column('folder_id', Uuid, nullable=True),
    Column('content_type', String, nullable=False),
    Column('source_platform', String, nullable=False),
    Column('source_url', Text, nullable=False),
    Column('normalized_url', Text, nullable=False),
    Column('external_id', String, nullable=True),
    Column('title', Text, nullable=False),
    Column('subtitle', Text, nullable=True),
    Column('author_name', String, nullable=True),
    Column('author_id', String, nullable=True),
    Column('cover_url', Text, nullable=True),
    Column('duration_seconds', Integer, nullable=True),
    Column('language', String, nullable=True),
    Column('published_at', DateTime(timezone=True), nullable=True),
    Column('imported_at', DateTime(timezone=True), nullable=False),
    Column('status', String, nullable=False),
    Column('visibility', String, nullable=False),
    Column('raw_meta', JSON, nullable=False),
    Column('fetch_hash', String, nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

content_snapshots = Table(
    'content_snapshots',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('content_item_id', Uuid, nullable=False),
    Column('snapshot_type', String, nullable=False),
    Column('storage_path', Text, nullable=True),
    Column('html_text', Text, nullable=True),
    Column('http_status', Integer, nullable=True),
    Column('content_hash', String, nullable=True),
    Column('fetched_at', DateTime(timezone=True), nullable=False),
    Column('source_headers', JSON, nullable=False),
    Column('extra', JSON, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

content_parsed_documents = Table(
    'content_parsed_documents',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('content_item_id', Uuid, nullable=False),
    Column('parser_name', String, nullable=False),
    Column('parser_version', String, nullable=False),
    Column('title', Text, nullable=True),
    Column('excerpt', Text, nullable=True),
    Column('byline', Text, nullable=True),
    Column('language', String, nullable=True),
    Column('plain_text', Text, nullable=False),
    Column('structured_blocks', JSON, nullable=False),
    Column('quality_score', Float, nullable=True),
    Column('source_snapshot_id', Uuid, nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

transcripts = Table(
    'transcripts',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('content_item_id', Uuid, nullable=False),
    Column('transcript_type', String, nullable=False),
    Column('provider_name', String, nullable=True),
    Column('model_name', String, nullable=True),
    Column('language', String, nullable=True),
    Column('full_text', Text, nullable=False),
    Column('segments', JSON, nullable=False),
    Column('confidence_score', Float, nullable=True),
    Column('source_snapshot_id', Uuid, nullable=True),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)

summaries = Table(
    'summaries',
    metadata,
    Column('id', Uuid, primary_key=True),
    Column('content_item_id', Uuid, nullable=False),
    Column('summary_type', String, nullable=False),
    Column('provider_name', String, nullable=True),
    Column('model_name', String, nullable=True),
    Column('version', Integer, nullable=False),
    Column('content', Text, nullable=False),
    Column('source_parsed_document_id', Uuid, nullable=True),
    Column('source_transcript_id', Uuid, nullable=True),
    Column('evidence', JSON, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column('updated_at', DateTime(timezone=True), server_default=func.now(), nullable=False),
)


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith('postgresql+'):
        return database_url
    if database_url.startswith('postgresql://'):
        return database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    if database_url.startswith('postgres://'):
        return database_url.replace('postgres://', 'postgresql+psycopg://', 1)
    return database_url


def build_engine(database_url: str) -> Engine:
    return create_engine(normalize_database_url(database_url), future=True, pool_pre_ping=True)


def now_utc() -> datetime:
    return datetime.now(UTC)


def row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        candidate = value.strip().replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            return None
    return None


def _is_deleted_raw_meta(raw_meta: Any) -> bool:
    if not isinstance(raw_meta, dict):
        return False
    return _coerce_datetime(raw_meta.get('deleted_at')) is not None


def claim_next_task(engine: Engine) -> dict[str, Any] | None:
    with engine.begin() as conn:
        now = now_utc()
        row = conn.execute(
            select(processing_tasks)
            .where(
                processing_tasks.c.status.in_([PENDING_STATUS, RETRYING_STATUS]),
                processing_tasks.c.task_type.in_(SUPPORTED_TASK_TYPES),
                or_(
                    processing_tasks.c.next_retry_at.is_(None),
                    processing_tasks.c.next_retry_at <= now,
                ),
            )
            .order_by(processing_tasks.c.priority.desc(), processing_tasks.c.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        ).mappings().first()
        if row is None:
            return None

        next_attempt_count = int(row['attempt_count'])
        if row['status'] == PENDING_STATUS:
            next_attempt_count += 1

        started_at = now_utc()
        conn.execute(
            update(processing_tasks)
            .where(processing_tasks.c.id == row['id'])
            .values(
                status=RUNNING_STATUS,
                attempt_count=next_attempt_count,
                started_at=started_at,
                finished_at=None,
                error_message=None,
                next_retry_at=None,
                updated_at=started_at,
            )
        )
        claimed = conn.execute(select(processing_tasks).where(processing_tasks.c.id == row['id'])).mappings().first()
        return row_to_dict(claimed)


def load_content_item(engine: Engine, item_id: str) -> dict[str, Any] | None:
    with engine.begin() as conn:
        row = conn.execute(select(content_items).where(content_items.c.id == UUID(item_id))).mappings().first()
        return row_to_dict(row)


def _fetch_summary(pipeline: dict[str, Any]) -> dict[str, Any]:
    fetch = dict(pipeline.get('fetch') or {})
    return {
        'mode': fetch.get('mode'),
        'status_code': fetch.get('status_code'),
        'content_type': fetch.get('content_type'),
        'final_url': fetch.get('final_url'),
        'error_message': fetch.get('error_message'),
    }


def _quality_payload(pipeline: dict[str, Any], persistable: dict[str, Any]) -> dict[str, Any] | None:
    quality = persistable.get('quality') or pipeline.get('quality')
    if isinstance(quality, dict):
        return quality
    return None


def _pipeline_summary(task: dict[str, Any], pipeline: dict[str, Any], quality: dict[str, Any] | None) -> dict[str, Any]:
    summary = {
        'task_id': str(task['id']),
        'task_type': task['task_type'],
        'source_url': pipeline.get('source_url'),
        'normalized_url': pipeline.get('normalized_url'),
        'host': pipeline.get('host'),
        'site_name': pipeline.get('site_name'),
    }
    if quality is not None:
        summary['quality_score'] = quality.get('value', quality.get('score'))
    selected_subtitle = pipeline.get('selected_subtitle')
    if isinstance(selected_subtitle, dict):
        summary['subtitle_language'] = selected_subtitle.get('language')
    video = pipeline.get('video')
    if isinstance(video, dict):
        summary['bvid'] = video.get('bvid')
        summary['cid'] = video.get('cid')
    return summary


def _has_summary_source(parsed_document: Any, transcript: Any) -> bool:
    if isinstance(transcript, dict):
        if str(transcript.get('full_text') or '').strip():
            return True
        if list(transcript.get('segments') or []):
            return True
    if isinstance(parsed_document, dict):
        if str(parsed_document.get('plain_text') or '').strip():
            return True
        if list(parsed_document.get('structured_blocks') or []):
            return True
    return False


def _enqueue_summary_task_if_needed(conn, task: dict[str, Any], item: dict[str, Any], parsed_document: Any, transcript: Any, now: datetime) -> None:
    if task['task_type'] == 'generate_summary':
        return
    if not _has_summary_source(parsed_document, transcript):
        return

    existing_task_id = conn.execute(
        select(processing_tasks.c.id)
        .where(
            processing_tasks.c.content_item_id == item['id'],
            processing_tasks.c.task_type == 'generate_summary',
            processing_tasks.c.status.in_([PENDING_STATUS, RUNNING_STATUS, RETRYING_STATUS]),
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_task_id is not None:
        return

    existing_summary_id = conn.execute(
        select(summaries.c.id)
        .where(
            summaries.c.content_item_id == item['id'],
            summaries.c.summary_type == 'short',
        )
        .limit(1)
    ).scalar_one_or_none()
    if existing_summary_id is not None:
        return

    conn.execute(
        processing_tasks.insert().values(
            id=uuid4(),
            content_item_id=item['id'],
            user_id=item['user_id'],
            task_type='generate_summary',
            status=PENDING_STATUS,
            priority=0,
            attempt_count=0,
            max_attempts=3,
            locked_by=None,
            payload={'steps': ['summarize'], 'source_task_id': str(task['id'])},
            result={},
            error_message=None,
            started_at=None,
            finished_at=None,
            next_retry_at=None,
            created_at=now,
            updated_at=now,
        )
    )


def _upsert_content_snapshot(conn, item_id: UUID, raw_snapshot: dict[str, Any] | None, fetch_payload: dict[str, Any], now: datetime) -> UUID | None:
    if not isinstance(raw_snapshot, dict):
        return None

    snapshot_type = str(raw_snapshot.get('snapshot_type') or '').strip()
    if not snapshot_type:
        return None

    content_hash = raw_snapshot.get('content_hash')
    existing_stmt = (
        select(content_snapshots.c.id)
        .where(
            content_snapshots.c.content_item_id == item_id,
            content_snapshots.c.snapshot_type == snapshot_type,
        )
        .order_by(content_snapshots.c.fetched_at.desc(), content_snapshots.c.created_at.desc())
        .limit(1)
    )
    if content_hash:
        existing_stmt = existing_stmt.where(content_snapshots.c.content_hash == content_hash)
    existing_id = conn.execute(existing_stmt).scalar_one_or_none()

    fetched_at = _coerce_datetime(raw_snapshot.get('fetched_at')) or now
    values = {
        'content_item_id': item_id,
        'snapshot_type': snapshot_type,
        'storage_path': raw_snapshot.get('storage_path'),
        'html_text': raw_snapshot.get('html'),
        'http_status': raw_snapshot.get('status_code'),
        'content_hash': content_hash,
        'fetched_at': fetched_at,
        'source_headers': dict(raw_snapshot.get('source_headers') or {}),
        'extra': {
            'final_url': raw_snapshot.get('final_url') or fetch_payload.get('final_url'),
            'content_type': raw_snapshot.get('content_type') or fetch_payload.get('content_type'),
            'mode': fetch_payload.get('mode'),
            'error_message': fetch_payload.get('error_message'),
        },
        'updated_at': now,
    }
    if existing_id is not None:
        conn.execute(update(content_snapshots).where(content_snapshots.c.id == existing_id).values(**values))
        return existing_id

    snapshot_id = uuid4()
    conn.execute(
        content_snapshots.insert().values(
            id=snapshot_id,
            created_at=now,
            **values,
        )
    )
    return snapshot_id


def _upsert_parsed_document(conn, item_id: UUID, parsed_payload: dict[str, Any] | None, snapshot_id: UUID | None, quality: dict[str, Any] | None, now: datetime) -> UUID | None:
    if not isinstance(parsed_payload, dict):
        return None

    parser_name = str(parsed_payload.get('parser_name') or '').strip() or 'unknown'
    parser_version = str(parsed_payload.get('parser_version') or '').strip() or 'v1'
    plain_text = str(parsed_payload.get('plain_text') or '').strip()
    structured_blocks = list(parsed_payload.get('structured_blocks') or [])
    if not plain_text and not structured_blocks:
        return None

    existing_id = conn.execute(
        select(content_parsed_documents.c.id)
        .where(
            content_parsed_documents.c.content_item_id == item_id,
            content_parsed_documents.c.parser_name == parser_name,
            content_parsed_documents.c.parser_version == parser_version,
        )
        .limit(1)
    ).scalar_one_or_none()

    values = {
        'content_item_id': item_id,
        'parser_name': parser_name,
        'parser_version': parser_version,
        'title': parsed_payload.get('title'),
        'excerpt': parsed_payload.get('excerpt'),
        'byline': parsed_payload.get('byline'),
        'language': parsed_payload.get('language'),
        'plain_text': plain_text,
        'structured_blocks': structured_blocks,
        'quality_score': parsed_payload.get('quality_score') or (quality or {}).get('score'),
        'source_snapshot_id': snapshot_id,
        'updated_at': now,
    }
    if existing_id is not None:
        conn.execute(update(content_parsed_documents).where(content_parsed_documents.c.id == existing_id).values(**values))
        return existing_id

    parsed_document_id = uuid4()
    conn.execute(
        content_parsed_documents.insert().values(
            id=parsed_document_id,
            created_at=now,
            **values,
        )
    )
    return parsed_document_id


def _upsert_transcript(conn, item_id: UUID, transcript_payload: dict[str, Any] | None, snapshot_id: UUID | None, now: datetime) -> UUID | None:
    if not isinstance(transcript_payload, dict):
        return None

    transcript_type = str(transcript_payload.get('transcript_type') or '').strip()
    full_text = str(transcript_payload.get('full_text') or '').strip()
    segments = list(transcript_payload.get('segments') or [])
    if not transcript_type or (not full_text and not segments):
        return None

    existing_id = conn.execute(
        select(transcripts.c.id)
        .where(
            transcripts.c.content_item_id == item_id,
            transcripts.c.transcript_type == transcript_type,
        )
        .order_by(transcripts.c.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    values = {
        'content_item_id': item_id,
        'transcript_type': transcript_type,
        'provider_name': transcript_payload.get('provider_name'),
        'model_name': transcript_payload.get('model_name'),
        'language': transcript_payload.get('language'),
        'full_text': full_text,
        'segments': segments,
        'confidence_score': transcript_payload.get('confidence_score'),
        'source_snapshot_id': snapshot_id,
        'updated_at': now,
    }
    if existing_id is not None:
        conn.execute(update(transcripts).where(transcripts.c.id == existing_id).values(**values))
        return existing_id

    transcript_id = uuid4()
    conn.execute(
        transcripts.insert().values(
            id=transcript_id,
            created_at=now,
            **values,
        )
    )
    return transcript_id


def _normalize_summary_rows(summaries_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(summaries_payload, list):
        return []

    rows: list[dict[str, Any]] = []
    for summary in summaries_payload:
        if not isinstance(summary, dict):
            continue
        summary_type = str(summary.get('summary_type') or '').strip()
        content = str(summary.get('content') or '').strip()
        if not summary_type or not content:
            continue
        version = summary.get('version')
        try:
            normalized_version = int(version) if version is not None else 1
        except (TypeError, ValueError):
            normalized_version = 1
        rows.append(
            {
                'summary_type': summary_type,
                'content': content,
                'provider_name': summary.get('provider_name'),
                'model_name': summary.get('model_name'),
                'version': normalized_version,
                'evidence': list(summary.get('evidence') or []),
            }
        )
    return rows


def _upsert_summaries(
    conn,
    item_id: UUID,
    summaries_payload: Any,
    parsed_document_id: UUID | None,
    transcript_id: UUID | None,
    now: datetime,
) -> None:
    if summaries_payload is None:
        return

    normalized_rows = _normalize_summary_rows(summaries_payload)
    existing_rows = conn.execute(
        select(summaries.c.id, summaries.c.summary_type, summaries.c.version).where(summaries.c.content_item_id == item_id)
    ).mappings().all()
    existing_map = {(row['summary_type'], int(row['version'])): row['id'] for row in existing_rows}
    seen_keys: set[tuple[str, int]] = set()

    for row in normalized_rows:
        key = (row['summary_type'], row['version'])
        seen_keys.add(key)
        values = {
            'content_item_id': item_id,
            'summary_type': row['summary_type'],
            'provider_name': row['provider_name'],
            'model_name': row['model_name'],
            'version': row['version'],
            'content': row['content'],
            'source_parsed_document_id': parsed_document_id,
            'source_transcript_id': transcript_id,
            'evidence': row['evidence'],
            'updated_at': now,
        }
        existing_id = existing_map.get(key)
        if existing_id is not None:
            conn.execute(update(summaries).where(summaries.c.id == existing_id).values(**values))
            continue
        conn.execute(
            summaries.insert().values(
                id=uuid4(),
                created_at=now,
                **values,
            )
        )

    stale_ids = [row_id for key, row_id in existing_map.items() if key not in seen_keys]
    if stale_ids:
        conn.execute(summaries.delete().where(summaries.c.id.in_(stale_ids)))


def complete_task(engine: Engine, task: dict[str, Any], item: dict[str, Any], result_payload: dict[str, Any]) -> None:
    now = now_utc()
    pipeline = dict(result_payload['pipeline'])
    persistable = dict(pipeline.get('persistable') or {})
    content_item_payload = dict(persistable.get('content_item') or {})
    content_item_meta = dict(content_item_payload.get('raw_meta') or {})
    raw_meta = dict(item.get('raw_meta') or {})
    raw_meta.update(content_item_meta)

    parsed_document = persistable.get('parsed_document')
    if parsed_document is not None:
        raw_meta['parsed_document'] = parsed_document

    transcript = persistable.get('transcript')
    if transcript is not None:
        raw_meta['transcript'] = transcript

    summaries_payload = persistable.get('summaries')
    if summaries_payload is not None:
        raw_meta['summaries'] = summaries_payload

    raw_meta['fetch'] = _fetch_summary(pipeline)

    quality = _quality_payload(pipeline, persistable)
    if quality is not None:
        raw_meta['quality'] = quality

    raw_meta['pipeline_summary'] = _pipeline_summary(task, pipeline, quality)
    raw_meta['last_task'] = {
        'task_id': str(task['id']),
        'task_type': task['task_type'],
        'status': 'success',
        'completed_at': now.isoformat(),
    }

    content_hash = content_item_meta.get('content_hash') or item.get('fetch_hash')
    published_at = _coerce_datetime(content_item_payload.get('published_at'))

    with engine.begin() as conn:
        current_item = conn.execute(select(content_items).where(content_items.c.id == item['id'])).mappings().first()
        if current_item is None or _is_deleted_raw_meta(current_item.get('raw_meta')):
            conn.execute(
                update(processing_tasks)
                .where(processing_tasks.c.id == task['id'])
                .values(
                    status=CANCELED_STATUS,
                    error_message='content item was deleted',
                    finished_at=now,
                    next_retry_at=None,
                    updated_at=now,
                )
            )
            return

        snapshot_id = _upsert_content_snapshot(
            conn,
            item['id'],
            persistable.get('raw_snapshot'),
            dict(pipeline.get('fetch') or {}),
            now,
        )
        parsed_document_id = _upsert_parsed_document(
            conn,
            item['id'],
            parsed_document if isinstance(parsed_document, dict) else None,
            snapshot_id,
            quality,
            now,
        )
        transcript_id = _upsert_transcript(
            conn,
            item['id'],
            transcript if isinstance(transcript, dict) else None,
            snapshot_id,
            now,
        )
        _upsert_summaries(conn, item['id'], summaries_payload, parsed_document_id, transcript_id, now)

        conn.execute(
            update(content_items)
            .where(content_items.c.id == item['id'])
            .values(
                title=content_item_payload.get('title') or item.get('title') or '未命名内容',
                subtitle=content_item_payload.get('subtitle', item.get('subtitle')),
                author_name=content_item_payload.get('author_name', item.get('author_name')),
                author_id=content_item_payload.get('author_id', item.get('author_id')),
                cover_url=content_item_payload.get('cover_url', item.get('cover_url')),
                duration_seconds=content_item_payload.get('duration_seconds', item.get('duration_seconds')),
                language=content_item_payload.get('language', item.get('language')),
                published_at=published_at or item.get('published_at'),
                status='completed',
                raw_meta=raw_meta,
                fetch_hash=content_hash,
                updated_at=now,
            )
        )
        conn.execute(
            update(processing_tasks)
            .where(processing_tasks.c.id == task['id'])
            .values(
                status=SUCCESS_STATUS,
                result=result_payload,
                error_message=None,
                finished_at=now,
                updated_at=now,
            )
        )
        _enqueue_summary_task_if_needed(conn, task, item, parsed_document, transcript, now)


def fail_task(engine: Engine, task: dict[str, Any], item: dict[str, Any] | None, error_message: str) -> None:
    now = now_utc()
    if item is not None:
        with engine.begin() as conn:
            current_item = conn.execute(select(content_items).where(content_items.c.id == item['id'])).mappings().first()
            if current_item is None or _is_deleted_raw_meta(current_item.get('raw_meta')):
                conn.execute(
                    update(processing_tasks)
                    .where(processing_tasks.c.id == task['id'])
                    .values(
                        status=CANCELED_STATUS,
                        error_message='content item was deleted',
                        finished_at=now,
                        next_retry_at=None,
                        updated_at=now,
                    )
                )
                return

    attempt_count = int(task['attempt_count'])
    max_attempts = int(task['max_attempts'])
    retryable = attempt_count < max_attempts
    raw_meta = dict(item.get('raw_meta') or {}) if item is not None else {}
    raw_meta.update(
        {
            'last_task': {
                'task_id': str(task['id']),
                'task_type': task['task_type'],
                'status': RETRYING_STATUS if retryable else FAILED_STATUS,
                'error_message': error_message,
                'failed_at': now.isoformat(),
            }
        }
    )

    task_values: dict[str, Any] = {
        'error_message': error_message,
        'updated_at': now,
    }
    item_values: dict[str, Any] = {}
    if retryable:
        next_attempt_count = attempt_count + 1
        delay_seconds = min(300, max(30, 30 * next_attempt_count))
        task_values.update(
            {
                'status': RETRYING_STATUS,
                'attempt_count': next_attempt_count,
                'next_retry_at': now + timedelta(seconds=delay_seconds),
                'finished_at': None,
            }
        )
        if item is not None:
            item_values['status'] = 'processing'
    else:
        task_values.update(
            {
                'status': FAILED_STATUS,
                'finished_at': now,
                'next_retry_at': None,
            }
        )
        if item is not None:
            item_values['status'] = 'failed'

    with engine.begin() as conn:
        if item is not None:
            item_values['raw_meta'] = raw_meta
            item_values['updated_at'] = now
            conn.execute(update(content_items).where(content_items.c.id == item['id']).values(**item_values))
        conn.execute(update(processing_tasks).where(processing_tasks.c.id == task['id']).values(**task_values))


def load_integration_config(engine: Engine, user_id: str, integration_key: str) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            select(integration_settings)
            .where(
                integration_settings.c.user_id == UUID(user_id),
                integration_settings.c.integration_key == integration_key,
            )
            .limit(1)
        ).mappings().first()
        if row is None:
            return {}
        config = dict(row.get('config') or {})
        config['is_enabled'] = bool(row.get('is_enabled'))
        return config


def load_transcription_provider_config(engine: Engine, user_id: str) -> dict[str, Any]:
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(model_providers)
                .where(
                    model_providers.c.user_id == UUID(user_id),
                    model_providers.c.is_enabled.is_(True),
                )
                .order_by(model_providers.c.created_at.asc())
            )
            .mappings()
            .all()
        )
        row = _select_provider_for_capability(rows, "asr")
        if row is None:
            return {}
        config = dict(row.get('config') or {})
        transcription_config = dict(config.get('transcription') or {})
        return {
            'provider_id': str(row['id']),
            'provider_name': row['provider_name'],
            'provider_type': row['provider_type'],
            'base_url': row['base_url'],
            'api_key': reveal_secret(row['api_key_encrypted']),
            'model_name': row['transcription_model'],
            'doubao_transcription': {
                'app_id': transcription_config.get('app_id'),
                'access_token': reveal_secret(transcription_config.get('access_token_encrypted')),
                'secret_key': reveal_secret(transcription_config.get('secret_key_encrypted')),
            },
        }


def load_visual_understanding_provider_config(engine: Engine, user_id: str) -> dict[str, Any]:
    with engine.begin() as conn:
        rows = (
            conn.execute(
                select(model_providers)
                .where(
                    model_providers.c.user_id == UUID(user_id),
                    model_providers.c.is_enabled.is_(True),
                )
                .order_by(model_providers.c.created_at.asc())
            )
            .mappings()
            .all()
        )
        row = _select_provider_for_capability(rows, "llm")
        if row is None or not row.get('api_key_encrypted') or not row.get('chat_model'):
            return {}
        config = dict(row.get('config') or {})
        input_capabilities = _input_capabilities_from_config(config)
        return {
            'provider_id': str(row['id']),
            'provider_name': row['provider_name'],
            'provider_type': row['provider_type'],
            'base_url': row['base_url'],
            'api_key': reveal_secret(row['api_key_encrypted']),
            'model_name': row['chat_model'],
            'input_capabilities': input_capabilities,
            'provider_config': config,
        }


def load_summary_provider_config(engine: Engine, user_id: str) -> dict[str, Any]:
    return load_visual_understanding_provider_config(engine, user_id)


def _select_provider_for_capability(rows: list[dict[str, Any]], capability: str):
    fallback = None
    for row in rows:
        config = dict(row.get('config') or {})
        provider_capability = str(config.get('capability') or '').strip().lower()
        if provider_capability == capability:
            return row
        if fallback is None:
            if capability == "llm" and row.get('chat_model'):
                fallback = row
            if capability == "asr" and (
                row.get('transcription_model') or dict(config.get('transcription') or {})
            ):
                fallback = row
    return fallback


def _input_capabilities_from_config(config: dict[str, Any]) -> list[str]:
    values = config.get('input_capabilities')
    if not isinstance(values, list):
        return ['text']
    allowed = ('text', 'image', 'audio', 'video')
    selected = {
        str(value or '').strip().lower()
        for value in values
        if str(value or '').strip().lower() in allowed
    }
    return [value for value in allowed if value in selected] or ['text']
