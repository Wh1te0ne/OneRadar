from __future__ import annotations

import socket

from app.services import feed_service


class _FakeHeaders:
    def __init__(self, content_type: str = "application/rss+xml", charset: str = "utf-8") -> None:
        self._content_type = content_type
        self._charset = charset

    def get_content_type(self) -> str:
        return self._content_type

    def get_content_charset(self) -> str:
        return self._charset


class _FakeResponse:
    def __init__(self, body: str, *, url: str) -> None:
        self.url = url
        self.headers = _FakeHeaders()
        self._body = body.encode("utf-8")

    def read(self, limit: int | None = None) -> bytes:
        return self._body if limit is None else self._body[:limit]

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeOpener:
    def __init__(self, body: str, *, url: str) -> None:
        self._body = body
        self._url = url

    def open(self, request, timeout: int = 12) -> _FakeResponse:
        return _FakeResponse(self._body, url=self._url)


def test_feed_preview_route_returns_parsed_items(client, monkeypatch) -> None:
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

    monkeypatch.setattr(
        feed_service.socket,
        "getaddrinfo",
        lambda host, port, type=socket.SOCK_STREAM: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.18.0.10", port))],
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

    assert response.status_code == 200
    body = response.json()
    assert body["site_title"] == "Python Insider"
    assert body["site_url"] == "https://blog.python.org/"
    assert body["description"] == "The official blog of the Python core development team."
    assert body["source_url"] == "https://blog.python.org/rss.xml"
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "Rust for CPython Progress Update April 2026"
    assert body["items"][0]["tags"] == ["Rust"]
    assert body["items"][1]["author"] == "Hugo van Kemenade"
