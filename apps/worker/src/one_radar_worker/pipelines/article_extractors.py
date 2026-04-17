from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    import trafilatura
except ImportError:  # pragma: no cover - optional dependency
    trafilatura = None

try:
    from readability import Document as ReadabilityDocument
except ImportError:  # pragma: no cover - optional dependency
    ReadabilityDocument = None

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "source",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._in_ignored_tag = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._in_ignored_tag = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._in_ignored_tag = False
        if tag in {"p", "br", "div", "li", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._in_ignored_tag:
            text = data.strip()
            if text:
                self._chunks.append(text)
                self._chunks.append(" ")

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self._chunks)).strip()


@dataclass(slots=True)
class ArticleMetadata:
    title: str | None
    site_name: str | None
    byline: str | None
    language: str | None
    excerpt: str | None


@dataclass(slots=True)
class ArticleExtractionDraft:
    strategy: str
    title: str | None
    site_name: str | None
    byline: str | None
    language: str | None
    excerpt: str | None
    body_text: str


def _clean_text(text: str) -> str:
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def _extract_tag_value(html: str, pattern: str) -> str | None:
    match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _extract_meta_content(html: str, key: str) -> str | None:
    patterns = [
        rf'<meta[^>]+property=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
        rf'<meta[^>]+name=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']+)["\'][^>]*>',
    ]
    for pattern in patterns:
        value = _extract_tag_value(html, pattern)
        if value:
            return value
    return None


def _html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    return _clean_text(extractor.text())


def _strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return _normalize_whitespace(unescape(text))


def _build_metadata(html: str, payload: dict[str, Any]) -> ArticleMetadata:
    title = (
        _normalize_whitespace(str(payload.get("title")))
        if payload.get("title")
        else _normalize_whitespace(_extract_meta_content(html, "og:title"))
        or _normalize_whitespace(_extract_tag_value(html, r"<title[^>]*>(.*?)</title>"))
    )
    language = (
        _normalize_whitespace(str(payload.get("language")))
        if payload.get("language")
        else _normalize_whitespace(_extract_tag_value(html, r'<html[^>]+lang=["\']([^"\']+)["\']'))
    )
    site_name = (
        _normalize_whitespace(str(payload.get("site_name")))
        if payload.get("site_name")
        else _normalize_whitespace(_extract_meta_content(html, "og:site_name"))
    )
    byline = (
        _normalize_whitespace(str(payload.get("byline")))
        if payload.get("byline")
        else _normalize_whitespace(_extract_meta_content(html, "author"))
        or _normalize_whitespace(_extract_meta_content(html, "article:author"))
        or _normalize_whitespace(_extract_meta_content(html, "twitter:data1"))
    )
    excerpt = (
        _normalize_whitespace(str(payload.get("excerpt")))
        if payload.get("excerpt")
        else _strip_html(_extract_meta_content(html, "description"))
        or _strip_html(_extract_meta_content(html, "og:description"))
    )
    return ArticleMetadata(
        title=title,
        site_name=site_name,
        byline=byline,
        language=language,
        excerpt=excerpt,
    )


def build_article_metadata(html: str, payload: dict[str, Any]) -> ArticleMetadata:
    return _build_metadata(html, payload)


def _extract_with_trafilatura(html: str, source_url: str) -> str | None:
    if trafilatura is None:
        return None
    try:
        text = trafilatura.extract(
            html,
            url=source_url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
            output_format="txt",
        )
    except Exception:  # pragma: no cover - extractor is best-effort
        return None
    if not text:
        return None
    return _clean_text(text)


def _extract_with_readability(html: str) -> tuple[str | None, str | None]:
    if ReadabilityDocument is None:
        return None, None
    try:
        document = ReadabilityDocument(html)
        summary_html = document.summary()
        title = _normalize_whitespace(document.title())
    except Exception:  # pragma: no cover - extractor is best-effort
        return None, None
    body_text = _html_to_text(summary_html)
    if not body_text:
        return None, None
    return title, body_text


def _extract_with_plain_text(html: str, payload: dict[str, Any]) -> str | None:
    provided_text = payload.get("text")
    if isinstance(provided_text, str) and provided_text.strip():
        return _clean_text(provided_text)
    text = _html_to_text(html)
    if text:
        return text
    fallback = _clean_text(re.sub(r"<[^>]+>", " ", html))
    return fallback or None


def _normalize_url(raw_url: str) -> str:
    trimmed = raw_url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", trimmed):
        trimmed = f"https://{trimmed}"

    parsed = urlsplit(trimmed)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if ":80" in netloc and scheme == "http":
        netloc = netloc.replace(":80", "")
    if ":443" in netloc and scheme == "https":
        netloc = netloc.replace(":443", "")

    query_pairs = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key not in _TRACKING_PARAMS]
    query = urlencode(query_pairs, doseq=True)
    fragment = ""
    path = re.sub(r"//+", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    return urlunsplit((scheme, netloc, path, query, fragment))


def extract_article_drafts(html: str, source_url: str, payload: dict[str, Any]) -> list[ArticleExtractionDraft]:
    metadata = build_article_metadata(html, payload)
    drafts: list[ArticleExtractionDraft] = []

    primary_text = _extract_with_trafilatura(html, source_url)
    if primary_text:
        drafts.append(
            ArticleExtractionDraft(
                strategy="trafilatura",
                title=metadata.title,
                site_name=metadata.site_name,
                byline=metadata.byline,
                language=metadata.language,
                excerpt=metadata.excerpt,
                body_text=primary_text,
            )
        )

    readability_title, readability_text = _extract_with_readability(html)
    if readability_text:
        drafts.append(
            ArticleExtractionDraft(
                strategy="readability",
                title=readability_title or metadata.title,
                site_name=metadata.site_name,
                byline=metadata.byline,
                language=metadata.language,
                excerpt=metadata.excerpt,
                body_text=readability_text,
            )
        )

    plain_text = _extract_with_plain_text(html, payload)
    if plain_text:
        drafts.append(
            ArticleExtractionDraft(
                strategy="plain_text",
                title=metadata.title,
                site_name=metadata.site_name,
                byline=metadata.byline,
                language=metadata.language,
                excerpt=metadata.excerpt,
                body_text=plain_text,
            )
        )

    return drafts
