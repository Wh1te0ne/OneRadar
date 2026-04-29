from __future__ import annotations

from pathlib import Path
import shutil
from uuid import uuid4

from one_radar_worker.pipelines.common import PipelineContext
from one_radar_worker.pipelines.podcast import PodcastPipeline
from one_radar_worker.tasks import TaskType


class _FakeResponse:
    status = 206
    url = "https://cdn.example.com/audio.m4a"

    def __init__(self) -> None:
        self.headers = {"Content-Type": "audio/mp4", "Content-Length": "4"}
        self._sent = False

    def read(self, size: int = -1) -> bytes:
        if self._sent:
            return b""
        self._sent = True
        return b"test-audio"

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_podcast_pipeline_downloads_audio_only_when_episode_task_runs(monkeypatch) -> None:
    monkeypatch.setattr("one_radar_worker.pipelines.podcast.urlopen", lambda request, timeout=120: _FakeResponse())

    media_root = Path("podcast-test-media").resolve()
    if media_root.exists():
        shutil.rmtree(media_root)
    media_root.mkdir(parents=True)
    item_id = uuid4()
    try:
        context = PipelineContext(
            item_id=item_id,
            source_url="https://example.com/episodes/1",
            task_type=TaskType.FETCH_META,
            payload={
                "title": "最新一期",
                "podcast_title": "凹凸电波",
                "feed_url": "https://example.com/podcast.xml",
                "episode_link": "https://example.com/episodes/1",
                "enclosure_url": "https://cdn.example.com/audio.m4a",
                "enclosure_type": "audio/x-m4a",
                "media_library_root": str(media_root),
            },
        )

        result = PodcastPipeline().run(context)

        assert result.ok is True
        persistable = result.data["persistable"]
        audio_path = Path(persistable["content_item"]["raw_meta"]["podcast"]["audio_storage_path"])
        assert audio_path.exists()
        assert audio_path.read_bytes() == b"test-audio"
        assert audio_path.parent == media_root / "podcasts" / str(item_id)
        assert persistable["raw_snapshot"]["snapshot_type"] == "podcast_audio"
        assert persistable["transcript"] is None
    finally:
        shutil.rmtree(media_root, ignore_errors=True)
