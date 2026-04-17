from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from .article_extractors import extract_article_drafts
from .common import (
    PipelineContext,
    PipelineDocumentBlock,
    PipelineQualityScore,
    PipelineRunResult,
    PipelineStepResult,
)

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


_BLOCKED_FETCH_HOSTS = {"localhost", "localhost.localdomain"}
_BLOCKED_FETCH_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")
_ALLOWED_FETCH_SCHEMES = {"http", "https"}
_ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}
_DOCKER_DESKTOP_PROXY_NETWORK = ipaddress.ip_network("198.18.0.0/15")


class UnsafeArticleUrlError(ValueError):
    pass


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _ensure_safe_fetch_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _is_blocked_public_address(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any((
        address.is_private,
        address.is_loopback,
        address.is_link_local,
        address.is_multicast,
        address.is_reserved,
        address.is_unspecified,
    ))


def _is_allowed_proxy_resolution_address(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address in _DOCKER_DESKTOP_PROXY_NETWORK


def _validate_fetch_target_components(normalized_url: str) -> tuple[str, int]:
    parsed = urlsplit(normalized_url)
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold()
    if scheme not in _ALLOWED_FETCH_SCHEMES:
        raise UnsafeArticleUrlError("only http and https URLs are supported")
    if not host:
        raise UnsafeArticleUrlError("url host is required")
    if parsed.username or parsed.password:
        raise UnsafeArticleUrlError("URLs with embedded credentials are not allowed")
    if host in _BLOCKED_FETCH_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_FETCH_SUFFIXES):
        raise UnsafeArticleUrlError("local or internal hosts are not allowed")
    if _is_blocked_public_address(host):
        raise UnsafeArticleUrlError("private or special-use IP addresses are not allowed")
    port = parsed.port or (443 if scheme == "https" else 80)
    return host, port


def _resolve_public_addresses(host: str, port: int) -> list[str]:
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise UnsafeArticleUrlError(f"host resolution failed: {error}") from error

    public_addresses: list[str] = []
    blocked_addresses: set[str] = set()
    for result in results:
        address_text = str(result[4][0]).split('%', 1)[0]
        if _is_allowed_proxy_resolution_address(address_text):
            public_addresses.append(address_text)
            continue
        if _is_blocked_public_address(address_text):
            blocked_addresses.add(address_text)
            continue
        public_addresses.append(address_text)

    if public_addresses:
        return public_addresses
    if blocked_addresses:
        raise UnsafeArticleUrlError("host resolves only to private or special-use IP addresses")
    raise UnsafeArticleUrlError("host resolution returned no usable public addresses")


def _ensure_safe_fetch_target(normalized_url: str) -> None:
    host, port = _validate_fetch_target_components(normalized_url)
    _resolve_public_addresses(host, port)

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


def _host_from_url(normalized_url: str) -> str:
    return urlsplit(normalized_url).netloc


def _site_name_from_host(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2].title()
    return host.title() or "Unknown"


def _clean_text(text: str) -> str:
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    return paragraphs


def _build_blocks(title: str | None, excerpt: str | None, paragraphs: list[str]) -> list[PipelineDocumentBlock]:
    blocks: list[PipelineDocumentBlock] = []
    if title:
        blocks.append(PipelineDocumentBlock(block_type="heading", text=title, order=0, data={"level": 1}))
    if excerpt:
        blocks.append(PipelineDocumentBlock(block_type="excerpt", text=excerpt, order=len(blocks)))
    for index, paragraph in enumerate(paragraphs, start=len(blocks)):
        blocks.append(PipelineDocumentBlock(block_type="paragraph", text=paragraph, order=index))
    return blocks


def _score_quality(title: str | None, body_text: str, html: str, site_name: str | None, excerpt: str | None) -> PipelineQualityScore:
    score = 0.0
    reasons: list[str] = []

    if title:
        score += 20
        reasons.append("title found")
    if site_name:
        score += 5
        reasons.append("site name resolved")
    if len(body_text) >= 120:
        score += 20
        reasons.append("body text length is usable")
    if len(body_text) >= 500:
        score += 20
        reasons.append("body text length is strong")
    paragraphs = _split_paragraphs(body_text)
    if len(paragraphs) >= 3:
        score += 15
        reasons.append("multiple paragraphs extracted")
    unique_words = len({word.lower() for word in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", body_text)})
    if unique_words >= 50:
        score += 15
        reasons.append("content has enough vocabulary variety")
    if excerpt:
        score += 5
        reasons.append("excerpt extracted")
    if re.search(r"<article|<main|<p", html, flags=re.IGNORECASE):
        score += 5
        reasons.append("semantic article markup detected")

    return PipelineQualityScore(value=min(score, 100.0), reasons=reasons)


def _choose_candidate(candidates: list["ArticleExtractionCandidate"]) -> "ArticleExtractionCandidate":
    for strategy in ("trafilatura", "readability", "plain_text"):
        preferred = [candidate for candidate in candidates if candidate.strategy == strategy]
        if preferred:
            return max(preferred, key=lambda candidate: candidate.quality.value)
    raise ValueError("no article extraction candidates available")


@dataclass(slots=True)
class ArticleFetchResult:
    mode: str
    source_url: str
    normalized_url: str
    final_url: str
    ok: bool
    status_code: int | None
    content_type: str | None
    html: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArticleExtractionCandidate:
    strategy: str
    title: str | None
    site_name: str | None
    byline: str | None
    language: str | None
    excerpt: str | None
    body_text: str
    blocks: list[PipelineDocumentBlock]
    quality: PipelineQualityScore

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blocks"] = [asdict(block) for block in self.blocks]
        payload["quality"] = asdict(self.quality)
        return payload


@dataclass(slots=True)
class ArticlePipelineOutput:
    source_url: str
    normalized_url: str
    host: str
    site_name: str
    fetch: ArticleFetchResult
    candidates: list[ArticleExtractionCandidate]
    chosen_candidate: ArticleExtractionCandidate
    persistable: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "normalized_url": self.normalized_url,
            "host": self.host,
            "site_name": self.site_name,
            "fetch": self.fetch.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "chosen_candidate": self.chosen_candidate.to_dict(),
            "persistable": self.persistable,
        }


@dataclass(slots=True)
class ArticlePipeline:
    """V1 article ingestion skeleton with normalization, fetch, and extraction stages."""

    def run(self, context: PipelineContext) -> PipelineRunResult:
        payload = dict(context.payload)
        raw_url = payload.get("source_url", context.source_url)
        normalized_url = _normalize_url(str(raw_url))
        host = _host_from_url(normalized_url)
        site_name = payload.get("site_name") or _site_name_from_host(host)

        steps: list[PipelineStepResult] = [
            PipelineStepResult(
                "normalize_url",
                True,
                "URL normalized",
                {
                    "source_url": raw_url,
                    "normalized_url": normalized_url,
                    "host": host,
                    "site_name": site_name,
                },
            )
        ]

        fetch_result = self._fetch_html(normalized_url, payload)
        steps.append(
            PipelineStepResult(
                "fetch_html",
                fetch_result.ok,
                "HTML fetched" if fetch_result.ok else (fetch_result.error_message or "Fetch fallback used"),
                fetch_result.to_dict(),
            )
        )

        candidates = self._extract_candidates(fetch_result, payload)
        chosen_candidate = _choose_candidate(candidates)
        steps.append(
            PipelineStepResult(
                "extract_article",
                bool(chosen_candidate.body_text),
                f"Selected {chosen_candidate.strategy}",
                chosen_candidate.to_dict(),
            )
        )

        persistable = self._build_persistable_output(
            source_url=str(raw_url),
            normalized_url=normalized_url,
            host=host,
            site_name=site_name,
            fetch_result=fetch_result,
            chosen_candidate=chosen_candidate,
        )
        steps.append(
            PipelineStepResult(
                "score_quality",
                True,
                "Quality scored",
                {"quality_score": chosen_candidate.quality.value, "reasons": chosen_candidate.quality.reasons},
            )
        )

        result = ArticlePipelineOutput(
            source_url=str(raw_url),
            normalized_url=normalized_url,
            host=host,
            site_name=site_name,
            fetch=fetch_result,
            candidates=candidates,
            chosen_candidate=chosen_candidate,
            persistable=persistable,
        )
        steps.append(
            PipelineStepResult(
                "build_persistable_payload",
                True,
                "Structured output prepared",
                persistable,
            )
        )

        ok = bool(chosen_candidate.body_text)
        return PipelineRunResult(ok=ok, steps=steps, data=result.to_dict())

    def _fetch_html(self, normalized_url: str, payload: dict[str, Any]) -> ArticleFetchResult:
        mode = str(payload.get("fetch_mode", "dry_run"))
        provided_html = payload.get("html")
        if isinstance(provided_html, str) and provided_html.strip():
            html = provided_html.strip()
            return ArticleFetchResult(
                mode="provided_html",
                source_url=str(payload.get("source_url", normalized_url)),
                normalized_url=normalized_url,
                final_url=normalized_url,
                ok=True,
                status_code=200,
                content_type="text/html",
                html=html,
            )

        if mode != "live":
            html = self._demo_html(normalized_url, payload)
            return ArticleFetchResult(
                mode=mode,
                source_url=str(payload.get("source_url", normalized_url)),
                normalized_url=normalized_url,
                final_url=normalized_url,
                ok=True,
                status_code=200,
                content_type="text/html",
                html=html,
            )

        try:
            _ensure_safe_fetch_target(normalized_url)
        except UnsafeArticleUrlError as error:
            html = self._demo_html(normalized_url, payload)
            return ArticleFetchResult(
                mode="blocked",
                source_url=str(payload.get("source_url", normalized_url)),
                normalized_url=normalized_url,
                final_url=normalized_url,
                ok=False,
                status_code=None,
                content_type=None,
                html=html,
                error_message=str(error),
            )

        request = Request(
            normalized_url,
            headers={
                "User-Agent": "OneRadarWorker/0.1",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        opener = build_opener(_SafeRedirectHandler())
        try:
            with opener.open(request, timeout=float(payload.get("timeout_seconds", 10))) as response:
                final_url = getattr(response, "url", normalized_url)
                _ensure_safe_fetch_target(final_url)
                content_type = response.headers.get_content_type()
                if content_type not in _ALLOWED_CONTENT_TYPES:
                    raise ValueError(f"unsupported content type: {content_type}")
                raw_body = response.read(int(payload.get("max_bytes", 2_000_000)))
                charset = response.headers.get_content_charset() or "utf-8"
                html = raw_body.decode(charset, errors="replace")
                return ArticleFetchResult(
                    mode="live",
                    source_url=str(payload.get("source_url", normalized_url)),
                    normalized_url=normalized_url,
                    final_url=final_url,
                    ok=True,
                    status_code=getattr(response, "status", 200),
                    content_type=content_type,
                    html=html,
                )
        except (HTTPError, URLError, TimeoutError, UnsafeArticleUrlError, ValueError) as error:
            html = self._demo_html(normalized_url, payload)
            return ArticleFetchResult(
                mode="live_fallback",
                source_url=str(payload.get("source_url", normalized_url)),
                normalized_url=normalized_url,
                final_url=normalized_url,
                ok=False,
                status_code=None,
                content_type=None,
                html=html,
                error_message=f"live fetch unavailable: {error}",
            )

    def _extract_candidates(self, fetch_result: ArticleFetchResult, payload: dict[str, Any]) -> list[ArticleExtractionCandidate]:
        html = fetch_result.html
        source_url = fetch_result.final_url or fetch_result.normalized_url
        drafts = extract_article_drafts(html, source_url, payload)
        candidates: list[ArticleExtractionCandidate] = []

        for draft in drafts:
            body_text = draft.body_text.strip()
            if not body_text:
                continue
            title = draft.title if draft.title else None
            site_name = draft.site_name if draft.site_name else None
            byline = draft.byline if draft.byline else None
            language = draft.language if draft.language else None
            excerpt = draft.excerpt if draft.excerpt else None
            blocks = _build_blocks(title, excerpt, _split_paragraphs(body_text))
            candidates.append(
                ArticleExtractionCandidate(
                    strategy=draft.strategy,
                    title=title,
                    site_name=site_name,
                    byline=byline,
                    language=language,
                    excerpt=excerpt,
                    body_text=body_text,
                    blocks=blocks,
                    quality=_score_quality(title, body_text, html, site_name, excerpt),
                )
            )

        if candidates:
            return candidates

        fallback_body = _clean_text(_html_to_text(html) or re.sub(r"<[^>]+>", " ", html))
        fallback_title = _extract_meta_content(html, "og:title") or _extract_tag_value(html, r"<title[^>]*>(.*?)</title>")
        fallback_excerpt = _extract_meta_content(html, "description") or _extract_meta_content(html, "og:description")
        fallback_site_name = _extract_meta_content(html, "og:site_name")
        fallback_blocks = _build_blocks(fallback_title, fallback_excerpt, _split_paragraphs(fallback_body))
        return [
            ArticleExtractionCandidate(
                strategy="plain_text",
                title=fallback_title if fallback_title else None,
                site_name=fallback_site_name if fallback_site_name else None,
                byline=None,
                language=None,
                excerpt=fallback_excerpt if fallback_excerpt else None,
                body_text=fallback_body,
                blocks=fallback_blocks,
                quality=_score_quality(
                    fallback_title if fallback_title else None,
                    fallback_body,
                    html,
                    fallback_site_name if fallback_site_name else None,
                    fallback_excerpt if fallback_excerpt else None,
                ),
            )
        ]


    def _primary_body_text(self, html: str, payload: dict[str, Any]) -> str:
        article_match = re.search(r"<article[^>]*>(.*?)</article>", html, flags=re.IGNORECASE | re.DOTALL)
        main_match = re.search(r"<main[^>]*>(.*?)</main>", html, flags=re.IGNORECASE | re.DOTALL)
        source = article_match.group(1) if article_match else main_match.group(1) if main_match else html
        text = _html_to_text(source)
        return text or self._fallback_body_text(html, payload)

    def _fallback_body_text(self, html: str, payload: dict[str, Any]) -> str:
        provided_text = payload.get("text")
        if isinstance(provided_text, str) and provided_text.strip():
            return _clean_text(provided_text)
        text = _html_to_text(html)
        if text:
            return text
        return _clean_text(re.sub(r"<[^>]+>", " ", html))

    def _demo_html(self, normalized_url: str, payload: dict[str, Any]) -> str:
        title = payload.get("title") or "OneRadar demo article"
        body = payload.get("text") or (
            "OneRadar keeps raw source material, cleaned text, and annotations separate.\n\n"
            "The worker pipeline normalizes URLs, fetches content, scores extraction quality, and prepares a persistable payload.\n\n"
            f"Source URL: {normalized_url}"
        )
        excerpt = payload.get("excerpt") or "A worker-side article pipeline skeleton with structured extraction output."
        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{title}</title>
  <meta name=\"description\" content=\"{excerpt}\" />
  <meta property=\"og:site_name\" content=\"OneRadar Demo\" />
</head>
<body>
  <article>
    <h1>{title}</h1>
    <p>{body.replace(chr(10), '</p><p>')}</p>
  </article>
</body>
</html>"""

    def _build_persistable_output(
        self,
        source_url: str,
        normalized_url: str,
        host: str,
        site_name: str,
        fetch_result: ArticleFetchResult,
        chosen_candidate: ArticleExtractionCandidate,
    ) -> dict[str, Any]:
        body_bytes = chosen_candidate.body_text.encode("utf-8")
        content_hash = hashlib.sha256(body_bytes + normalized_url.encode("utf-8")).hexdigest()
        return {
            "content_item": {
                "source_url": source_url,
                "normalized_url": normalized_url,
                "source_platform": "web",
                "content_type": "article",
                "title": chosen_candidate.title or site_name or host,
                "author_name": chosen_candidate.byline,
                "language": chosen_candidate.language,
                "status": "processing",
                "raw_meta": {
                    "site_name": site_name,
                    "host": host,
                    "author_name": chosen_candidate.byline,
                    "byline": chosen_candidate.byline,
                    "title": chosen_candidate.title,
                    "excerpt": chosen_candidate.excerpt,
                    "extraction_strategy": chosen_candidate.strategy,
                    "content_hash": content_hash,
                },
            },
            "raw_snapshot": {
                "snapshot_type": "article_html",
                "content_hash": content_hash,
                "content_type": fetch_result.content_type,
                "status_code": fetch_result.status_code,
                "final_url": fetch_result.final_url,
                "html": fetch_result.html,
            },
            "parsed_document": {
                "source_url": source_url,
                "normalized_url": normalized_url,
                "site_name": site_name,
                "parser_name": chosen_candidate.strategy,
                "parser_version": "v1",
                "title": chosen_candidate.title,
                "excerpt": chosen_candidate.excerpt,
                "author_name": chosen_candidate.byline,
                "byline": chosen_candidate.byline,
                "plain_text": chosen_candidate.body_text,
                "structured_blocks": [
                    {
                        "type": block.block_type,
                        "text": block.text,
                        "order": block.order,
                        "data": block.data,
                    }
                    for block in chosen_candidate.blocks
                ],
                "quality_score": chosen_candidate.quality.value,
                "extraction_strategy": chosen_candidate.strategy,
            },
            "quality": {
                "score": chosen_candidate.quality.value,
                "reasons": chosen_candidate.quality.reasons,
            },
            "summary_inputs": {
                "source_url": source_url,
                "normalized_url": normalized_url,
                "site_name": site_name,
                "quality_score": chosen_candidate.quality.value,
                "author_name": chosen_candidate.byline,
                "byline": chosen_candidate.byline,
                "excerpt": chosen_candidate.excerpt,
                "extraction_strategy": chosen_candidate.strategy,
            },
            "fetch": fetch_result.to_dict(),
        }



def _demo_article_payload(source_url: str) -> dict[str, Any]:
    return {
        "fetch_mode": "dry_run",
        "title": "Durable Reading Workflow for OneRadar",
        "site_name": "OneRadar Demo",
        "excerpt": "A skeleton article pipeline that can be persisted later.",
        "text": (
            "OneRadar should store raw HTML, a cleaned reading version, and the user\'s annotations separately.\n\n"
            "The worker pipeline normalizes URLs, generates extraction candidates, scores quality, and prepares structured data for the API.\n\n"
            "Later stages can summarize the article, build search indexes, and attach notes and highlights."
        ),
        "source_url": source_url,
    }



