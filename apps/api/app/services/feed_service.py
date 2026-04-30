from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET

from app.schemas.feeds import FeedArticlePreviewResponse, FeedPreviewItem, FeedPreviewResponse
from app.services.items_service import find_saved_item_for_url
from app.services.url_safety import (
    is_allowed_proxy_resolution_address,
    is_blocked_public_address,
    validate_public_http_url,
)

ATOM_NS = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
DC_NS = "http://purl.org/dc/elements/1.1/"
ALLOWED_FEED_CONTENT_TYPES = {
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
}
DEFAULT_FEED_LIMIT = 12
MAX_FEED_LIMIT = 40
MAX_ARTICLE_BYTES = 2_500_000
HN_ARTICLE_URL_RE = re.compile(r"\bArticle URL:\s*(https?://\S+)", re.IGNORECASE)


class UnsafeFeedUrlError(ValueError):
    pass


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _ensure_safe_fetch_target(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def _strip_html(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return _normalize_whitespace(unescape(text))


def _extract_hn_article_url(summary: str | None) -> str | None:
    if not summary or "Comments URL:" not in summary or "Article URL:" not in summary:
        return None
    match = HN_ARTICLE_URL_RE.search(summary)
    if not match:
        return None
    candidate = match.group(1).rstrip(").,;]")
    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.netloc:
        return None
    return candidate


def _apply_saved_state(item: FeedPreviewItem) -> FeedPreviewItem:
    saved = find_saved_item_for_url(item.link)
    if saved is None:
        return item
    item.is_saved = True
    item.saved_item_id = saved["item_id"]
    item.saved_uid = saved["uid"]
    return item


def _parse_datetime(value: str | None) -> datetime | None:
    normalized = _normalize_whitespace(value)
    if not normalized:
        return None
    try:
        parsed = parsedate_to_datetime(normalized)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (TypeError, ValueError, IndexError, OverflowError):
        pass
    try:
        iso_candidate = normalized.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso_candidate)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(node: ET.Element, *names: str) -> str | None:
    for child in node:
        if _local_name(child.tag) in names:
            if child.text and child.text.strip():
                return child.text.strip()
    return None


def _child_all_text(node: ET.Element, *names: str) -> list[str]:
    values: list[str] = []
    for child in node:
        if _local_name(child.tag) in names:
            if child.text and child.text.strip():
                values.append(child.text.strip())
    return values


def _resolve_public_addresses(host: str, port: int) -> list[str]:
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise UnsafeFeedUrlError(f"host resolution failed: {error}") from error

    public_addresses: list[str] = []
    blocked_addresses: set[str] = set()
    for result in results:
        address_text = str(result[4][0]).split('%', 1)[0]
        try:
            address = ipaddress.ip_address(address_text)
        except ValueError:
            continue
        if is_allowed_proxy_resolution_address(address_text):
            public_addresses.append(str(address))
            continue
        if is_blocked_public_address(address_text):
            blocked_addresses.add(str(address))
            continue
        public_addresses.append(str(address))

    if public_addresses:
        return public_addresses
    if blocked_addresses:
        raise UnsafeFeedUrlError("host resolves only to private or special-use IP addresses")
    raise UnsafeFeedUrlError("host resolution returned no usable public addresses")


def _ensure_safe_fetch_target(url: str) -> None:
    validate_public_http_url(url)
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    port = parsed.port or (443 if parsed.scheme.casefold() == "https" else 80)
    _resolve_public_addresses(host, port)


def _read_feed_xml(source_url: str) -> tuple[str, str, str | None]:
    _ensure_safe_fetch_target(source_url)
    request = Request(
        source_url,
        headers={
            "User-Agent": "OneRadarAPI/0.1",
            "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.1",
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=12) as response:
            final_url = getattr(response, "url", source_url)
            _ensure_safe_fetch_target(final_url)
            content_type = response.headers.get_content_type()
            raw_body = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            xml_text = raw_body.decode(charset, errors="replace")
            return xml_text, final_url, content_type
    except (HTTPError, URLError, TimeoutError, UnsafeFeedUrlError, ValueError) as error:
        raise ValueError(f"feed fetch failed: {error}") from error


def _read_article_html(source_url: str) -> tuple[str, str, str | None]:
    _ensure_safe_fetch_target(source_url)
    request = Request(
        source_url,
        headers={
            "User-Agent": "OneRadarAPI/0.1",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=12) as response:
            final_url = getattr(response, "url", source_url)
            _ensure_safe_fetch_target(final_url)
            content_type = response.headers.get_content_type()
            raw_body = response.read(MAX_ARTICLE_BYTES)
            charset = response.headers.get_content_charset() or "utf-8"
            html_text = raw_body.decode(charset, errors="replace")
            return html_text, final_url, content_type
    except (HTTPError, URLError, TimeoutError, UnsafeFeedUrlError, ValueError) as error:
        raise ValueError(f"article fetch failed: {error}") from error


class _ReadableHtmlParser(HTMLParser):
    _ignored_tags = {"script", "style", "noscript", "svg", "canvas", "form", "iframe", "nav", "header", "footer"}
    _block_tags = {"article", "main", "section", "p", "li", "blockquote", "pre", "h1", "h2", "h3", "h4", "div"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.author: str | None = None
        self.description: str | None = None
        self.site_title: str | None = None
        self._title_parts: list[str] = []
        self._current_parts: list[str] = []
        self._article_blocks: list[str] = []
        self._body_blocks: list[str] = []
        self._ignore_depth = 0
        self._body_depth = 0
        self._article_depth = 0
        self._main_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.casefold()
        attrs_map = {key.casefold(): (value or "") for key, value in attrs}
        if name in self._ignored_tags:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if name == "body":
            self._body_depth += 1
        elif name == "article":
            self._flush_current()
            self._article_depth += 1
        elif name == "main":
            self._flush_current()
            self._main_depth += 1
        elif name == "title":
            self._in_title = True
        elif name == "meta":
            self._capture_meta(attrs_map)
        elif name in self._block_tags:
            self._flush_current()
        elif name == "br":
            self._flush_current()

    def handle_endtag(self, tag: str) -> None:
        name = tag.casefold()
        if name in self._ignored_tags and self._ignore_depth:
            self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if name == "title":
            self._in_title = False
            self.title = _normalize_whitespace(" ".join(self._title_parts)) or self.title
            self._title_parts = []
            return
        if name in self._block_tags or name == "br":
            self._flush_current()
        if name == "article" and self._article_depth:
            self._article_depth -= 1
        elif name == "main" and self._main_depth:
            self._main_depth -= 1
        elif name == "body" and self._body_depth:
            self._body_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._body_depth or self._article_depth or self._main_depth:
            self._current_parts.append(data)

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _capture_meta(self, attrs: dict[str, str]) -> None:
        content = _normalize_whitespace(attrs.get("content"))
        if not content:
            return
        key = (attrs.get("name") or attrs.get("property") or "").casefold()
        if key in {"og:title", "twitter:title"} and not self.title:
            self.title = content
        elif key in {"author", "article:author", "byl"} and not self.author:
            self.author = content
        elif key in {"description", "og:description", "twitter:description"} and not self.description:
            self.description = content
        elif key in {"og:site_name", "application-name"} and not self.site_title:
            self.site_title = content

    def _flush_current(self) -> None:
        text = _normalize_whitespace(" ".join(self._current_parts))
        self._current_parts = []
        if not text:
            return
        target = self._article_blocks if self._article_depth or self._main_depth else self._body_blocks
        if not target or target[-1] != text:
            target.append(text)

    def plain_text(self) -> str | None:
        blocks = self._article_blocks if self._article_blocks else self._body_blocks
        cleaned: list[str] = []
        for block in blocks:
            if len(block) < 2:
                continue
            if cleaned and cleaned[-1] == block:
                continue
            cleaned.append(block)
        text = "\n\n".join(cleaned).strip()
        return text or None


def _drop_duplicate_title_block(plain_text: str, title: str) -> str:
    blocks = [block.strip() for block in plain_text.split("\n\n") if block.strip()]
    if not blocks:
        return plain_text
    if _normalize_whitespace(blocks[0]) == _normalize_whitespace(title):
        return "\n\n".join(blocks[1:]).strip() or plain_text
    return plain_text


def _parse_rss_item(item: ET.Element) -> FeedPreviewItem | None:
    title = _normalize_whitespace(_child_text(item, "title"))
    link = _normalize_whitespace(_child_text(item, "link"))
    if not title or not link:
        return None
    guid = _normalize_whitespace(_child_text(item, "guid"))
    summary = _strip_html(_child_text(item, "description", "encoded"))
    link = _extract_hn_article_url(summary) or link
    author = _normalize_whitespace(_child_text(item, "creator", "author"))
    published_at = _parse_datetime(_child_text(item, "pubDate", "date", "published", "updated"))
    tags = [_normalize_whitespace(value) for value in _child_all_text(item, "category")]
    return FeedPreviewItem(
        id=guid or link,
        title=title,
        link=link,
        summary=summary,
        author=author,
        published_at=published_at,
        tags=[value for value in tags if value],
    )


def _parse_atom_entry(entry: ET.Element, feed_url: str) -> FeedPreviewItem | None:
    title = _normalize_whitespace(_child_text(entry, "title"))
    link: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        rel = (child.attrib.get("rel") or "alternate").casefold()
        href = _normalize_whitespace(child.attrib.get("href"))
        if href and rel == "alternate":
            link = urljoin(feed_url, href)
            break
        if href and link is None:
            link = urljoin(feed_url, href)
    if not title or not link:
        return None
    summary = _strip_html(_child_text(entry, "summary", "content"))
    author = None
    for child in entry:
        if _local_name(child.tag) != "author":
            continue
        author = _normalize_whitespace(_child_text(child, "name"))
        if author:
            break
    published_at = _parse_datetime(_child_text(entry, "published", "updated"))
    entry_id = _normalize_whitespace(_child_text(entry, "id")) or link
    tags = []
    for child in entry:
        if _local_name(child.tag) != "category":
            continue
        term = _normalize_whitespace(child.attrib.get("term") or child.attrib.get("label") or child.text)
        if term:
            tags.append(term)
    return FeedPreviewItem(
        id=entry_id,
        title=title,
        link=link,
        summary=summary,
        author=author,
        published_at=published_at,
        tags=tags,
    )


def _parse_feed(xml_text: str, source_url: str, limit: int) -> FeedPreviewResponse:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as error:
        raise ValueError(f"feed parse failed: {error}") from error

    root_name = _local_name(root.tag).casefold()
    items: list[FeedPreviewItem] = []
    site_title = source_url
    site_url: str | None = None
    description: str | None = None

    if root_name in {"rss", "rdf"}:
        channel = next((child for child in root if _local_name(child.tag) == "channel"), root)
        site_title = _normalize_whitespace(_child_text(channel, "title")) or source_url
        site_url = _normalize_whitespace(_child_text(channel, "link"))
        description = _strip_html(_child_text(channel, "description"))
        for child in channel:
            if _local_name(child.tag) != "item":
                continue
            parsed = _parse_rss_item(child)
            if parsed is not None:
                items.append(parsed)
            if len(items) >= limit:
                break
    elif root_name == "feed":
        site_title = _normalize_whitespace(_child_text(root, "title")) or source_url
        description = _strip_html(_child_text(root, "subtitle"))
        for child in root:
            if _local_name(child.tag) == "link":
                rel = (child.attrib.get("rel") or "alternate").casefold()
                href = _normalize_whitespace(child.attrib.get("href"))
                if href and rel == "alternate":
                    site_url = urljoin(source_url, href)
                    break
                if href and site_url is None:
                    site_url = urljoin(source_url, href)
            if _local_name(child.tag) != "entry":
                continue
            parsed = _parse_atom_entry(child, source_url)
            if parsed is not None:
                items.append(parsed)
            if len(items) >= limit:
                break
    else:
        raise ValueError("unsupported feed format")

    items.sort(key=lambda item: item.published_at or datetime.fromtimestamp(0, tz=UTC), reverse=True)
    items = [_apply_saved_state(item) for item in items]
    return FeedPreviewResponse(
        source_url=source_url,
        site_title=site_title,
        site_url=site_url,
        description=description,
        items=items[:limit],
        fetched_at=datetime.now(UTC),
    )


def preview_feed(url: str, limit: int = DEFAULT_FEED_LIMIT) -> FeedPreviewResponse:
    source_url = url.strip()
    if not source_url:
        raise ValueError("feed url is required")
    normalized_limit = max(1, min(limit, MAX_FEED_LIMIT))
    xml_text, final_url, content_type = _read_feed_xml(source_url)
    if content_type and content_type not in ALLOWED_FEED_CONTENT_TYPES and "xml" not in content_type:
        raise ValueError(f"unsupported feed content type: {content_type}")
    response = _parse_feed(xml_text, final_url, normalized_limit)
    response.source_url = final_url
    return response


def preview_feed_article(
    url: str,
    *,
    title: str | None = None,
    source_title: str | None = None,
    author: str | None = None,
    published_at: str | None = None,
    summary: str | None = None,
) -> FeedArticlePreviewResponse:
    source_url = url.strip()
    if not source_url:
        raise ValueError("article url is required")

    html_text, final_url, content_type = _read_article_html(source_url)
    if content_type and "html" not in content_type and content_type not in {"text/plain", "application/octet-stream"}:
        raise ValueError(f"unsupported article content type: {content_type}")

    parser = _ReadableHtmlParser()
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as error:  # HTMLParser can surface malformed entity edge cases.
        raise ValueError(f"article parse failed: {error}") from error

    fallback_summary = _strip_html(summary)
    plain_text = parser.plain_text() or fallback_summary
    if not plain_text:
        raise ValueError("article preview did not contain readable text")

    parsed_title = _normalize_whitespace(parser.title) or _normalize_whitespace(title) or final_url
    plain_text = _drop_duplicate_title_block(plain_text, parsed_title)
    saved = find_saved_item_for_url(final_url) or find_saved_item_for_url(source_url)
    return FeedArticlePreviewResponse(
        source_url=source_url,
        final_url=final_url,
        title=parsed_title,
        site_title=_normalize_whitespace(parser.site_title) or _normalize_whitespace(source_title),
        author=_normalize_whitespace(parser.author) or _normalize_whitespace(author),
        published_at=_parse_datetime(published_at),
        summary=_normalize_whitespace(parser.description) or fallback_summary,
        plain_text=plain_text,
        fetched_at=datetime.now(UTC),
        is_saved=saved is not None,
        saved_item_id=saved["item_id"] if saved else None,
        saved_uid=saved["uid"] if saved else None,
        can_generate_ai=saved is not None,
    )


