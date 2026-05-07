from __future__ import annotations

from uuid import uuid4

from one_radar_worker.pipelines import article, article_extractors
from one_radar_worker.pipelines.article_extractors import ArticleExtractionDraft
from one_radar_worker.pipelines.common import PipelineContext
from one_radar_worker.tasks import TaskType


def test_extract_article_drafts_returns_primary_fallback_and_plain_text(monkeypatch):
    class FakeTrafilatura:
        @staticmethod
        def extract(html, url, include_comments, include_tables, favor_recall, output_format):
            assert url == "https://example.com/story"
            return "Primary body text\n\nSecond paragraph"

    class FakeReadabilityDocument:
        def __init__(self, html):
            self.html = html

        def summary(self):
            return "<article><p>Fallback body text</p></article>"

        def title(self):
            return "Fallback Title"

    monkeypatch.setattr(article_extractors, "trafilatura", FakeTrafilatura)
    monkeypatch.setattr(article_extractors, "ReadabilityDocument", FakeReadabilityDocument)

    html = """<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8" />
  <title>Payload Title</title>
  <meta name="description" content="Payload excerpt" />
  <meta name="author" content="Payload Author" />
  <meta property="og:site_name" content="Payload Site" />
</head>
<body>
  <article>
    <h1>Payload Title</h1>
    <p>Primary body text</p>
  </article>
</body>
</html>"""

    drafts = article_extractors.extract_article_drafts(
        html,
        "https://example.com/story",
        {"title": "Payload Title", "byline": "Payload Author"},
    )

    assert [draft.strategy for draft in drafts] == ["trafilatura", "readability", "plain_text"]
    assert drafts[0].byline == "Payload Author"
    assert drafts[1].title == "Fallback Title"
    assert "Primary body text" in drafts[0].body_text
    assert "Fallback body text" in drafts[1].body_text
    assert "Payload Title" in drafts[2].body_text


def test_pipeline_prefers_primary_candidate_and_persists_byline(monkeypatch):
    primary = ArticleExtractionDraft(
        strategy="trafilatura",
        title="Primary Title",
        site_name="Primary Site",
        byline="Primary Author",
        language="zh",
        excerpt="Primary excerpt",
        body_text="Primary body text with enough substance for scoring.",
    )
    fallback = ArticleExtractionDraft(
        strategy="readability",
        title="Fallback Title",
        site_name="Fallback Site",
        byline="Fallback Author",
        language="zh",
        excerpt="Fallback excerpt",
        body_text="Fallback body text that is intentionally longer than the primary candidate to ensure strategy order matters.",
    )
    fetch_result = article.ArticleFetchResult(
        mode="provided_html",
        source_url="https://example.com/story",
        normalized_url="https://example.com/story",
        final_url="https://example.com/story",
        ok=True,
        status_code=200,
        content_type="text/html",
        html="<html><body><article><p>Primary body text</p></article></body></html>",
    )

    monkeypatch.setattr(article, "extract_article_drafts", lambda html, source_url, payload: [fallback, primary])
    monkeypatch.setattr(article.ArticlePipeline, "_fetch_html", lambda self, normalized_url, payload: fetch_result)

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://example.com/story",
        task_type=TaskType.EXTRACT_ARTICLE,
        payload={"fetch_mode": "live"},
    )

    result = article.ArticlePipeline().run(context)

    assert result.ok is True
    assert result.data["chosen_candidate"]["strategy"] == "trafilatura"
    persistable = result.data["persistable"]
    assert persistable["content_item"]["author_name"] == "Primary Author"
    assert persistable["content_item"]["raw_meta"]["extraction_strategy"] == "trafilatura"
    assert persistable["parsed_document"]["parser_name"] == "trafilatura"
    assert persistable["parsed_document"]["author_name"] == "Primary Author"
    assert persistable["parsed_document"]["byline"] == "Primary Author"
    assert persistable["parsed_document"]["plain_text"].startswith("Primary body text")


def test_pipeline_uses_first_body_line_when_extractor_title_is_missing(monkeypatch):
    draft = ArticleExtractionDraft(
        strategy="trafilatura",
        title=None,
        site_name=None,
        byline=None,
        language="en",
        excerpt=None,
        body_text="Voice & TTS\nHermes Agent supports text-to-speech output.",
    )
    fetch_result = article.ArticleFetchResult(
        mode="live",
        source_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        normalized_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        final_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        ok=True,
        status_code=200,
        content_type="text/html",
        html="<html><body><main><p>Voice & TTS</p></main></body></html>",
    )

    monkeypatch.setattr(article, "extract_article_drafts", lambda html, source_url, payload: [draft])
    monkeypatch.setattr(article.ArticlePipeline, "_fetch_html", lambda self, normalized_url, payload: fetch_result)

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        task_type=TaskType.EXTRACT_ARTICLE,
        payload={"fetch_mode": "live"},
    )

    result = article.ArticlePipeline().run(context)

    persistable = result.data["persistable"]
    assert persistable["content_item"]["title"] == "Voice & TTS"
    assert persistable["parsed_document"]["title"] == "Voice & TTS"


def test_pipeline_replaces_placeholder_title_with_first_body_line(monkeypatch):
    draft = ArticleExtractionDraft(
        strategy="trafilatura",
        title="新导入内容",
        site_name="Nousresearch",
        byline=None,
        language="en",
        excerpt=None,
        body_text="Voice & TTS\nHermes Agent supports text-to-speech output.",
    )
    fetch_result = article.ArticleFetchResult(
        mode="live",
        source_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        normalized_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        final_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        ok=True,
        status_code=200,
        content_type="text/html",
        html="<html><body><main><p>Voice & TTS</p></main></body></html>",
    )

    monkeypatch.setattr(article, "extract_article_drafts", lambda html, source_url, payload: [draft])
    monkeypatch.setattr(article.ArticlePipeline, "_fetch_html", lambda self, normalized_url, payload: fetch_result)

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://hermes-agent.nousresearch.com/docs/user-guide/features/tts",
        task_type=TaskType.EXTRACT_ARTICLE,
        payload={"title": "新导入内容", "fetch_mode": "live"},
    )

    result = article.ArticlePipeline().run(context)

    persistable = result.data["persistable"]
    assert persistable["content_item"]["title"] == "Voice & TTS"


def test_live_fetch_failure_does_not_persist_demo_article(monkeypatch):
    def reject_url(normalized_url):
        raise article.UnsafeArticleUrlError("blocked for test")

    monkeypatch.setattr(article, "_ensure_safe_fetch_target", reject_url)

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://example.com/story",
        task_type=TaskType.EXTRACT_ARTICLE,
        payload={"fetch_mode": "live"},
    )

    result = article.ArticlePipeline().run(context)

    assert result.ok is False
    assert result.data["fetch"]["html"] == ""
    assert "OneRadar demo article" not in result.data["chosen_candidate"]["body_text"]
    assert result.data["chosen_candidate"]["body_text"] == ""


def test_pipeline_preserves_heading_levels_from_extracted_body(monkeypatch):
    html = """<!doctype html>
<html>
<body>
  <nav><h2>Navigation heading</h2></nav>
  <article>
    <h1>Article Title</h1>
    <p>Lead paragraph.</p>
    <h2>First Section</h2>
    <p>First section body.</p>
    <h3>Nested Point</h3>
    <p>Nested body.</p>
  </article>
</body>
</html>"""
    draft = ArticleExtractionDraft(
        strategy="trafilatura",
        title="Article Title",
        site_name="Example",
        byline=None,
        language="en",
        excerpt=None,
        body_text="Article Title\n\nLead paragraph.\n\nFirst Section\n\nFirst section body.\n\nNested Point\n\nNested body.",
    )
    fetch_result = article.ArticleFetchResult(
        mode="live",
        source_url="https://example.com/story",
        normalized_url="https://example.com/story",
        final_url="https://example.com/story",
        ok=True,
        status_code=200,
        content_type="text/html",
        html=html,
    )

    monkeypatch.setattr(article, "extract_article_drafts", lambda html, source_url, payload: [draft])
    monkeypatch.setattr(article.ArticlePipeline, "_fetch_html", lambda self, normalized_url, payload: fetch_result)

    context = PipelineContext(
        item_id=uuid4(),
        source_url="https://example.com/story",
        task_type=TaskType.EXTRACT_ARTICLE,
        payload={"fetch_mode": "live"},
    )

    result = article.ArticlePipeline().run(context)

    blocks = result.data["persistable"]["parsed_document"]["structured_blocks"]
    heading_blocks = [block for block in blocks if block["type"] == "heading"]
    assert [block["text"] for block in heading_blocks] == ["Article Title", "First Section", "Nested Point"]
    assert [block["data"]["level"] for block in heading_blocks] == [1, 2, 3]
    assert all(block["text"] != "Navigation heading" for block in blocks)
