from __future__ import annotations

import socket
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.services import feed_service, feed_state_service, items_service


class _FakeHeaders:
    def __init__(self, content_type: str = "application/rss+xml", charset: str = "utf-8") -> None:
        self._content_type = content_type
        self._charset = charset

    def get_content_type(self) -> str:
        return self._content_type

    def get_content_charset(self) -> str:
        return self._charset


class _FakeResponse:
    def __init__(self, body: str, *, url: str, content_type: str = "application/rss+xml") -> None:
        self.url = url
        self.headers = _FakeHeaders(content_type=content_type)
        self._body = body.encode("utf-8")

    def read(self, limit: int | None = None) -> bytes:
        return self._body if limit is None else self._body[:limit]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeOpener:
    def __init__(self, body: str, *, url: str, content_type: str = "application/rss+xml") -> None:
        self._body = body
        self._url = url
        self._content_type = content_type

    def open(self, request, timeout: int = 12) -> _FakeResponse:
        return _FakeResponse(self._body, url=self._url, content_type=self._content_type)


def _public_getaddrinfo(host, port, type=socket.SOCK_STREAM):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.10", port))]


def test_feed_preview_route_returns_parsed_items(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    rss_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>Python Insider</title>
        <link>https://blog.python.org/</link>
        <description>The official blog of the Python core development team.</description>
        <item>
          <title>Rust for CPython Progress Update April 2026</title>
          <link>https://blog.python.org/2026/04/rust-for-cpython-2026-04/</link>
          <guid>https://blog.python.org/2026/04/rust-for-cpython-2026-04/</guid>
          <description>Rust for CPython project status update April 2026</description>
          <author>Emma Smith</author>
          <pubDate>Tue, 08 Apr 2026 00:00:00 GMT</pubDate>
          <category>Rust</category>
        </item>
        <item>
          <title>Python 3.15.0a8, 3.14.4 and 3.13.13 are out!</title>
          <link>https://blog.python.org/2026/04/python-3150a8-3144-31313/</link>
          <guid>https://blog.python.org/2026/04/python-3150a8-3144-31313/</guid>
          <description>A final alpha and two bug fixes are awaiting your upgrade.</description>
          <author>Hugo van Kemenade</author>
          <pubDate>Mon, 07 Apr 2026 00:00:00 GMT</pubDate>
          <category>releases</category>
        </item>
      </channel>
    </rss>"""

    import_response = client.post(
        "/api/items/import",
        json={
            "url": "https://blog.python.org/2026/04/rust-for-cpython-2026-04/",
            "source_hint": "article",
        },
    )
    assert import_response.status_code == 200, import_response.json()

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        _public_getaddrinfo,
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(rss_xml, url="https://blog.python.org/rss.xml"),
    )

    response = client.get(
        "/api/feeds/preview",
        params={"url": "https://blog.python.org/rss.xml", "limit": 2},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["site_title"] == "Python Insider"
    assert body["site_url"] == "https://blog.python.org/"
    assert body["description"] == "The official blog of the Python core development team."
    assert body["source_url"] == "https://blog.python.org/rss.xml"
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "Rust for CPython Progress Update April 2026"
    assert body["items"][0]["tags"] == ["Rust"]
    assert body["items"][0]["is_saved"] is True
    assert body["items"][0]["saved_item_id"] == import_response.json()["item_id"]
    assert body["items"][1]["is_saved"] is False
    assert body["items"][1]["author"] == "Hugo van Kemenade"


def test_feed_preview_limit_zero_returns_all_feed_items(client, monkeypatch) -> None:
    items = "\n".join(
        f"""
        <item>
          <title>Entry {index}</title>
          <link>https://example.com/entry-{index}</link>
          <guid>entry-{index}</guid>
          <pubDate>Thu, 30 Apr 2026 {index % 24:02d}:00:00 GMT</pubDate>
        </item>
        """
        for index in range(45)
    )
    rss_xml = f"""<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>Large Feed</title>
        <link>https://example.com/</link>
        {items}
      </channel>
    </rss>"""

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        lambda host, port, type=socket.SOCK_STREAM: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.10", port))
        ],
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(rss_xml, url="https://example.com/rss.xml"),
    )

    response = client.get(
        "/api/feeds/preview",
        params={"url": "https://example.com/rss.xml", "limit": 0},
    )

    assert response.status_code == 200, response.json()
    assert len(response.json()["items"]) == 45


def test_feed_preview_prefers_hn_article_url_from_summary(client, monkeypatch) -> None:
    rss_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>Hacker News</title>
        <link>https://news.ycombinator.com/</link>
        <item>
          <title>Interesting article</title>
          <link>https://news.ycombinator.com/item?id=47950377</link>
          <guid>https://news.ycombinator.com/item?id=47950377</guid>
          <description>
            Article URL: https://example.com/story
            Comments URL: https://news.ycombinator.com/item?id=47950377
            Points: 20 # Comments: 2
          </description>
          <pubDate>Tue, 28 Apr 2026 00:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>"""

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        _public_getaddrinfo,
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(rss_xml, url="https://hnrss.org/frontpage"),
    )

    response = client.get(
        "/api/feeds/preview",
        params={"url": "https://hnrss.org/frontpage", "limit": 1},
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["items"][0]["link"] == "https://example.com/story"


def test_feed_preview_parses_atom_entries_after_site_link(client, monkeypatch) -> None:
    atom_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom'>
      <title>Example Atom</title>
      <link rel='alternate' type='text/html' href='https://example.com/' />
      <link rel='self' type='application/atom+xml' href='https://example.com/feed.xml' />
      <entry>
        <title>First Atom Entry</title>
        <link rel='alternate' type='text/html' href='https://example.com/first' />
        <id>tag:example.com,2026:first</id>
        <published>2026-05-07T01:00:00Z</published>
        <summary>Atom summary</summary>
        <author><name>Atom Author</name></author>
        <category term='AI' />
      </entry>
    </feed>"""

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        lambda host, port, type=socket.SOCK_STREAM: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.10", port))
        ],
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(
            atom_xml,
            url="https://example.com/feed.xml",
            content_type="application/atom+xml",
        ),
    )

    response = client.get("/api/feeds/preview", params={"url": "https://example.com/feed.xml"})

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["site_url"] == "https://example.com/"
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "First Atom Entry"
    assert body["items"][0]["author"] == "Atom Author"


def test_feed_article_preview_route_returns_clean_reader_text(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(items_service, "SessionLocal", failing_session_local)

    html = """<!doctype html>
    <html>
      <head>
        <title>Readable Title</title>
        <meta name="author" content="Ada Reporter">
        <meta property="og:site_name" content="Example Daily">
        <meta name="description" content="A short article summary.">
      </head>
      <body>
        <nav>navigation should not appear</nav>
        <article>
          <h1>Readable Title</h1>
          &lt; img id=&quot;wx_img&quot; src=&quot;https://www.qbitai.com/logo.png&quot;
            width=&quot;400&quot; height=&quot;400&quot;&gt;
          <p>First paragraph with useful reporting.</p>
          <p>Second paragraph with enough detail for the reader view.</p>
          <p>量子位的朋友们</p>
          <p>相关阅读</p>
          <p>各大应用商店都能下载</p>
        </article>
        <footer>footer should not appear</footer>
      </body>
    </html>"""

    import_response = client.post(
        "/api/items/import",
        json={"url": "https://example.com/story", "source_hint": "article"},
    )
    assert import_response.status_code == 200, import_response.json()

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        _public_getaddrinfo,
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(
            html,
            url="https://example.com/story",
            content_type="text/html",
        ),
    )

    response = client.get(
        "/api/feeds/article-preview",
        params={
            "url": "https://example.com/story",
            "title": "Fallback Title",
            "source_title": "Fallback Source",
            "published_at": "2026-04-29T12:30:00Z",
        },
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["title"] == "Readable Title"
    assert body["site_title"] == "Example Daily"
    assert body["author"] == "Ada Reporter"
    assert body["is_saved"] is True
    assert body["saved_item_id"] == import_response.json()["item_id"]
    assert body["can_generate_ai"] is True
    assert "First paragraph with useful reporting." in body["plain_text"]
    assert "navigation should not appear" not in body["plain_text"]
    assert "wx_img" not in body["plain_text"]
    assert "<img" not in body["plain_text"]
    assert "量子位的朋友们" not in body["plain_text"]
    assert "相关阅读" not in body["plain_text"]


def test_feed_state_routes_persist_cache_and_read_markers(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(feed_state_service, "SessionLocal", failing_session_local)
    state_path = Path(".tmp") / f"feed-state-{uuid4().hex}.json"
    monkeypatch.setenv("ONERADAR_FEED_STATE_PATH", str(state_path))

    feed_payload = {
        "source_url": "https://example.com/rss.xml",
        "site_title": "Example Feed",
        "site_url": "https://example.com/",
        "description": "Example description",
        "items": [
            {
                "id": "entry-1",
                "title": "Entry One",
                "link": "https://example.com/entry-1",
                "summary": "Summary",
                "author": "Author",
                "published_at": "2026-04-30T00:00:00Z",
                "tags": ["tag"],
            }
        ],
        "fetched_at": "2026-04-30T01:00:00Z",
    }

    cache_response = client.post("/api/feeds/cache", json={"feed": feed_payload})
    assert cache_response.status_code == 200, cache_response.json()
    assert cache_response.json()["sources"][0]["source_url"] == "https://example.com/rss.xml"

    read_response = client.post("/api/feeds/read", json={"entry_key": "https://example.com/rss.xml:entry-1"})
    assert read_response.status_code == 200, read_response.json()
    assert "https://example.com/rss.xml:entry-1" in read_response.json()["read_entries"]

    state_response = client.get("/api/feeds/state")
    assert state_response.status_code == 200, state_response.json()
    state = state_response.json()
    assert state["feeds"]["https://example.com/rss.xml"]["items"][0]["title"] == "Entry One"
    assert state["read_entries"] == ["https://example.com/rss.xml:entry-1"]

    delete_response = client.delete("/api/feeds/sources", params={"url": "https://example.com/rss.xml"})
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True
    assert client.get("/api/feeds/state").json()["feeds"] == {}
    state_path.unlink(missing_ok=True)


def test_feed_state_routes_persist_source_refresh_errors(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(feed_state_service, "SessionLocal", failing_session_local)
    state_path = Path(".tmp") / f"feed-state-{uuid4().hex}.json"
    monkeypatch.setenv("ONERADAR_FEED_STATE_PATH", str(state_path))

    response = client.post(
        "/api/feeds/sources/error",
        json={
            "source_url": "https://example.com/rss.xml",
            "site_title": "Example Feed",
            "error_message": "Not Found",
        },
    )

    assert response.status_code == 200, response.json()
    source = response.json()["sources"][0]
    assert source["source_url"] == "https://example.com/rss.xml"
    assert source["site_title"] == "Example Feed"
    assert source["last_refresh_status"] == "failed"
    assert source["last_refresh_error"] == "Not Found"
    state_path.unlink(missing_ok=True)


def test_feed_refresh_route_refreshes_cached_sources(client, monkeypatch) -> None:
    def failing_session_local():
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(feed_state_service, "SessionLocal", failing_session_local)
    state_path = Path(".tmp") / f"feed-state-{uuid4().hex}.json"
    monkeypatch.setenv("ONERADAR_FEED_STATE_PATH", str(state_path))

    feed_payload = {
        "source_url": "https://example.com/rss.xml",
        "site_title": "Old Feed",
        "site_url": "https://example.com/",
        "description": None,
        "items": [],
        "fetched_at": "2026-04-30T01:00:00Z",
    }
    assert client.post("/api/feeds/cache", json={"feed": feed_payload}).status_code == 200

    rss_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>New Feed</title>
        <link>https://example.com/</link>
        <item>
          <title>New Entry</title>
          <link>https://example.com/new-entry</link>
          <guid>entry-new</guid>
          <description>Fresh summary</description>
          <pubDate>Thu, 30 Apr 2026 00:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>"""

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        _public_getaddrinfo,
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(rss_xml, url="https://example.com/rss.xml"),
    )

    response = client.post("/api/feeds/refresh")

    assert response.status_code == 200, response.json()
    assert response.json() == {"total": 1, "refreshed": 1, "failed": 0, "errors": {}}
    state = client.get("/api/feeds/state").json()
    assert state["feeds"]["https://example.com/rss.xml"]["site_title"] == "New Feed"
    assert state["feeds"]["https://example.com/rss.xml"]["items"][0]["title"] == "New Entry"
    state_path.unlink(missing_ok=True)


def test_feed_refresh_keeps_existing_db_entries_not_in_latest_feed(client, monkeypatch) -> None:
    feed_payload = {
        "source_url": "https://example.com/rss.xml",
        "site_title": "Example Feed",
        "site_url": "https://example.com/",
        "description": None,
        "items": [
            {
                "id": "entry-old",
                "title": "Old Entry",
                "link": "https://example.com/old-entry",
                "summary": "Stored from an earlier refresh",
                "author": "Author",
                "published_at": "2026-04-01T00:00:00Z",
                "tags": [],
            }
        ],
        "fetched_at": "2026-04-01T01:00:00Z",
    }
    assert client.post("/api/feeds/cache", json={"feed": feed_payload}).status_code == 200

    rss_xml = """<?xml version='1.0' encoding='UTF-8'?>
    <rss version='2.0'>
      <channel>
        <title>Example Feed</title>
        <link>https://example.com/</link>
        <item>
          <title>New Entry</title>
          <link>https://example.com/new-entry</link>
          <guid>entry-new</guid>
          <description>Fresh summary</description>
          <pubDate>Thu, 30 Apr 2026 00:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>"""

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        lambda host, port, type=socket.SOCK_STREAM: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.10", port))
        ],
    )
    monkeypatch.setattr(
        feed_service,
        "build_opener",
        lambda *args, **kwargs: _FakeOpener(rss_xml, url="https://example.com/rss.xml"),
    )

    response = client.post("/api/feeds/refresh")

    assert response.status_code == 200, response.json()
    entries = client.get("/api/feeds/state").json()["feeds"]["https://example.com/rss.xml"]["items"]
    titles = {entry["title"] for entry in entries}
    assert {"Old Entry", "New Entry"} <= titles
