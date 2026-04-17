from __future__ import annotations

from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit


BLOCKED_PUBLIC_HOSTS = {"localhost", "localhost.localdomain"}
BLOCKED_PUBLIC_SUFFIXES = (".local", ".localhost", ".internal", ".home.arpa")
ALLOWED_PUBLIC_SCHEMES = {"http", "https"}
_DOCKER_DESKTOP_PROXY_NETWORK = ip_network("198.18.0.0/15")


def is_blocked_public_address(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def is_allowed_proxy_resolution_address(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    # Docker Desktop and similar desktop-network stacks may proxy outbound DNS
    # resolution through 198.18.0.0/15. Keep these blocked as direct user input,
    # but allow them as hostname-resolution artifacts during outbound fetches.
    return address in _DOCKER_DESKTOP_PROXY_NETWORK


def validate_public_http_url(normalized_url: str) -> None:
    parsed = urlsplit(normalized_url)
    scheme = parsed.scheme.casefold()
    host = (parsed.hostname or "").casefold()
    if scheme not in ALLOWED_PUBLIC_SCHEMES:
        raise ValueError("only http and https URLs are supported")
    if not host:
        raise ValueError("url host is required")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not allowed")
    if host in BLOCKED_PUBLIC_HOSTS or any(host.endswith(suffix) for suffix in BLOCKED_PUBLIC_SUFFIXES):
        raise ValueError("local or internal hosts are not allowed")
    if is_blocked_public_address(host):
        raise ValueError("private or special-use IP addresses are not allowed")
