from __future__ import annotations

from typing import Literal

ContentType = Literal['article', 'bilibili_video']
SourcePlatform = Literal['web', 'bilibili']
ContentStatus = Literal['pending', 'processing', 'completed', 'failed', 'archived']
TaskStatus = Literal['pending', 'running', 'retrying', 'success', 'failed', 'canceled']
TaskType = Literal[
    'fetch_meta',
    'fetch_html',
    'extract_article',
    'fetch_subtitles',
    'extract_audio',
    'transcribe_audio',
    'generate_summary',
    'build_index',
    'reprocess_item',
    'sync_provider_test',
]
ProviderType = Literal['openai_compatible', 'doubao', 'custom']
