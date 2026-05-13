from __future__ import annotations

from uuid import UUID

from .pipelines.article import ArticlePipeline
from .pipelines.bilibili import BilibiliPipeline
from .pipelines.common import PipelineContext
from .pipelines.podcast import PodcastPipeline
from .pipelines.summary import SummaryPipeline
from .storage import (
    complete_task,
    fail_task,
    load_content_item,
    load_integration_config,
    load_summary_provider_config,
    load_transcription_provider_config,
    load_visual_understanding_provider_config,
)
from .tasks import TaskResult, TaskStatus, TaskType


SUPPORTED_CONTENT_TYPES = {'article', 'bilibili_video', 'podcast_episode'}



def _integration_payload(engine, item: dict[str, object]) -> dict[str, object]:
    if str(item.get('content_type') or '') != 'bilibili_video':
        return {}
    config = load_integration_config(engine, str(item['user_id']), 'bilibili')
    if not config or not config.get('is_enabled'):
        return {}
    return {'bilibili': config}


def _build_pipeline_payload(task: dict[str, object], item: dict[str, object]) -> dict[str, object]:
    payload = dict(task.get('payload') or {})
    raw_meta = dict(item.get('raw_meta') or {})
    source_url = str(payload.get('source_url') or payload.get('url') or item.get('source_url') or '')
    merged = dict(raw_meta)
    merged.update(payload)
    merged.setdefault('source_url', source_url)
    merged.setdefault('content_type', item.get('content_type'))
    merged.setdefault('title', item.get('title'))
    merged.setdefault('subtitle', item.get('subtitle'))
    merged.setdefault('author_name', item.get('author_name'))
    merged.setdefault('author_id', item.get('author_id'))
    merged.setdefault('cover_url', item.get('cover_url'))
    merged.setdefault('duration_seconds', item.get('duration_seconds'))
    merged.setdefault('language', item.get('language'))
    merged.setdefault('site_name', raw_meta.get('site_name'))
    if str(item.get('content_type') or '') == 'article':
        merged.setdefault('fetch_mode', 'live')
    if str(item.get('content_type') or '') == 'podcast_episode':
        podcast_meta = dict(raw_meta.get('podcast') or {})
        for key, value in podcast_meta.items():
            merged.setdefault(key, value)
    return merged


def _provider_payload(engine, item: dict[str, object]) -> dict[str, object]:
    if str(item.get('content_type') or '') not in {'bilibili_video', 'podcast_episode'}:
        return {}
    config = load_transcription_provider_config(engine, str(item['user_id']))
    if not config:
        return {}
    return {'transcription_provider': config}


def _summary_provider_payload(engine, item: dict[str, object]) -> dict[str, object]:
    config = load_summary_provider_config(engine, str(item['user_id']))
    if not config:
        return {}
    return {'summary_provider': config}


def _visual_provider_payload(engine, item: dict[str, object], integration_payload: dict[str, object]) -> dict[str, object]:
    if str(item.get('content_type') or '') != 'bilibili_video':
        return {}
    config = load_visual_understanding_provider_config(engine, str(item['user_id']))
    input_capabilities = {
        str(value or '').strip().lower()
        for value in list(config.get('input_capabilities') or [])
    }
    if not input_capabilities.intersection({'video', 'image', 'audio'}):
        return {}
    payload: dict[str, object] = {
        'visual_enhancement': {
            'enabled': True,
            'source': 'provider_input_capabilities',
        }
    }
    payload['visual_understanding_provider'] = config
    return payload


def _select_pipeline(item: dict[str, object]):
    if item.get('_task_type') == TaskType.GENERATE_SUMMARY.value:
        return SummaryPipeline()
    content_type = str(item.get('content_type') or '')
    if content_type == 'article':
        return ArticlePipeline()
    if content_type == 'bilibili_video':
        return BilibiliPipeline()
    if content_type == 'podcast_episode':
        return PodcastPipeline()
    raise ValueError(f'unsupported content type: {content_type}')


def _pipeline_failure_message(result) -> str:
    preferred_failure_steps = {
        'fetch_metadata',
        'extract_audio',
        'transcribe_audio',
        'generate_summary',
    }
    for step in result.steps:
        if step.step_name in preferred_failure_steps and not step.ok and step.message:
            return step.message
    for step in reversed(result.steps):
        if not step.ok and step.message:
            return step.message
    return 'content pipeline did not produce usable output'


def run_task(engine, task: dict[str, object]) -> TaskResult:
    item = load_content_item(engine, str(task['content_item_id']))
    if item is None:
        error_message = 'content item not found'
        fail_task(engine, task, None, error_message)
        return TaskResult(status=TaskStatus.FAILED, message=error_message, data={})

    try:
        if task['task_type'] not in {TaskType.FETCH_META.value, TaskType.REPROCESS_ITEM.value, TaskType.GENERATE_SUMMARY.value}:
            raise ValueError(f"unsupported task type: {task['task_type']}")
        if str(item.get('content_type') or '') not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(f"unsupported content type: {item.get('content_type')}")

        pipeline_payload = _build_pipeline_payload(task, item)
        integration_payload = _integration_payload(engine, item)
        if integration_payload:
            pipeline_payload['integration_config'] = integration_payload
        provider_payload = _provider_payload(engine, item)
        if provider_payload:
            pipeline_payload.update(provider_payload)
        visual_provider_payload = _visual_provider_payload(engine, item, integration_payload)
        if visual_provider_payload:
            pipeline_payload.update(visual_provider_payload)
        if task['task_type'] == TaskType.GENERATE_SUMMARY.value:
            summary_provider_payload = _summary_provider_payload(engine, item)
            if summary_provider_payload:
                pipeline_payload.update(summary_provider_payload)
            item = {**item, '_task_type': TaskType.GENERATE_SUMMARY.value}
        source_url = str(pipeline_payload.get('source_url') or item['source_url'])
        context = PipelineContext(
            item_id=UUID(str(item['id'])),
            source_url=source_url,
            task_type=TaskType(task['task_type']),
            payload=pipeline_payload,
        )
        result = _select_pipeline(item).run(context)
        result_payload = {
            'ok': result.ok,
            'pipeline': result.data,
            'source_url': source_url,
            'task_id': str(task['id']),
            'item_id': str(item['id']),
            'content_type': str(item.get('content_type') or ''),
        }
        if not result.ok:
            raise ValueError(_pipeline_failure_message(result))

        complete_task(engine, task, item, result_payload)
        return TaskResult(
            status=TaskStatus.SUCCESS,
            message='content pipeline completed',
            data=result_payload,
        )
    except Exception as exc:  # noqa: BLE001
        fail_task(engine, task, item, str(exc))
        retryable = int(task.get('attempt_count', 0)) < int(task.get('max_attempts', 0))
        status = TaskStatus.RETRYING if retryable else TaskStatus.FAILED
        return TaskResult(
            status=status,
            message=str(exc),
            data={'task_id': str(task['id']), 'item_id': str(item['id'])},
        )
