"""SSRF-safe URL checks for registry fetches."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

_BLOCKED_SCHEMES = frozenset({"http", "https"})

_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
)


def _allowed_hosts() -> frozenset[str]:
    raw = os.getenv("BUTLER_REGISTRY_ALLOWED_HOSTS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def _addr_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    for net in _PRIVATE_NETWORKS:
        if addr in net:
            return True
    return False


def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.scheme not in _BLOCKED_SCHEMES:
        return False
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False
    allowed = _allowed_hosts()
    if allowed and host in allowed:
        return True
    if host in ("localhost", "metadata.google.internal", "metadata.google"):
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        addr = ipaddress.ip_address(host)
        if _addr_blocked(addr):
            return False
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(host, None):
            ip = info[4][0]
            addr = ipaddress.ip_address(ip)
            if _addr_blocked(addr):
                return False
    except OSError:
        return False
    return True


def httpx_fetch_kwargs() -> dict:
    """Registry HTTP clients should not follow redirects (SSRF hardening)."""
    return {"follow_redirects": False, "timeout": 25.0}


def assert_safe_redirect(url: str) -> bool:
    """Re-validate Location target when a single manual redirect is needed."""
    return is_safe_url(url)


def safe_registry_get(url: str, **kwargs: object) -> object:
    """HTTP GET with no auto-redirects and one validated Location hop."""
    import httpx
    from urllib.parse import urljoin

    if not is_safe_url(url):
        raise ValueError(f"unsafe registry url: {url}")
    fetch_kw = httpx_fetch_kwargs()
    fetch_kw.update(kwargs)
    resp = httpx.get(url, **fetch_kw)
    if resp.status_code in (301, 302, 303, 307, 308):
        loc = resp.headers.get("location") or resp.headers.get("Location")
        if loc:
            next_url = urljoin(url, loc)
            if assert_safe_redirect(next_url):
                return httpx.get(next_url, **fetch_kw)
    return resp
