from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html import unescape
import ipaddress
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET

from app.schemas.feeds import FeedPreviewItem, FeedPreviewResponse
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


def _parse_rss_item(item: ET.Element) -> FeedPreviewItem | None:
    title = _normalize_whitespace(_child_text(item, "title"))
    link = _normalize_whitespace(_child_text(item, "link"))
    if not title or not link:
        return None
    guid = _normalize_whitespace(_child_text(item, "guid"))
    summary = _strip_html(_child_text(item, "description", "encoded"))
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


