from __future__ import annotations

from uuid import UUID

from .pipelines.article import ArticlePipeline
from .pipelines.bilibili import BilibiliPipeline
from .pipelines.common import PipelineContext
from .storage import complete_task, fail_task, load_content_item, load_integration_config
from .tasks import TaskResult, TaskStatus, TaskType


SUPPORTED_CONTENT_TYPES = {'article', 'bilibili_video'}



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
    merged.setdefault('title', item.get('title'))
    merged.setdefault('language', item.get('language'))
    merged.setdefault('site_name', raw_meta.get('site_name'))
    if str(item.get('content_type') or '') == 'article':
        merged.setdefault('fetch_mode', 'live')
    return merged


def _select_pipeline(item: dict[str, object]):
    content_type = str(item.get('content_type') or '')
    if content_type == 'article':
        return ArticlePipeline()
    if content_type == 'bilibili_video':
        return BilibiliPipeline()
    raise ValueError(f'unsupported content type: {content_type}')


def run_task(engine, task: dict[str, object]) -> TaskResult:
    item = load_content_item(engine, str(task['content_item_id']))
    if item is None:
        error_message = 'content item not found'
        fail_task(engine, task, None, error_message)
        return TaskResult(status=TaskStatus.FAILED, message=error_message, data={})

    try:
        if task['task_type'] not in {TaskType.FETCH_META.value, TaskType.REPROCESS_ITEM.value}:
            raise ValueError(f"unsupported task type: {task['task_type']}")
        if str(item.get('content_type') or '') not in SUPPORTED_CONTENT_TYPES:
            raise ValueError(f"unsupported content type: {item.get('content_type')}")

        pipeline_payload = _build_pipeline_payload(task, item)
        integration_payload = _integration_payload(engine, item)
        if integration_payload:
            pipeline_payload['integration_config'] = integration_payload
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
            raise ValueError('content pipeline did not produce usable output')

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
