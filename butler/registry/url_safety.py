"""SSRF-safe URL checks for registry fetches."""

from __future__ import annotations

import contextlib
import ipaddress
import os
import socket
from collections.abc import Iterator
from typing import Any
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
    from butler.registry.url_safety_ops import urlparse_safe

    parsed = urlparse_safe(url)
    if parsed is None:
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


def httpx_fetch_kwargs() -> dict[str, Any]:
    """Registry HTTP clients should not follow redirects (SSRF hardening)."""
    return {"follow_redirects": False, "timeout": 25.0}


def assert_safe_redirect(url: str) -> bool:
    """Re-validate Location target when a single manual redirect is needed."""
    return is_safe_url(url)


@contextlib.contextmanager
def _pinned_dns(host_to_ips: dict[str, list[str]]) -> Iterator[None]:
    """Pin host → list of IPs for the duration of the context.

    Sprint 22-2 SEC-21-A-3: DNS rebinding mitigation. `is_safe_url`
    resolves and validates IPs; `safe_registry_get` re-resolves and
    re-validates, then enters this context. For the duration of
    `httpx.get`, `socket.getaddrinfo` for the target host returns
    only the validated IP literals. A rebinding attack that flips
    the A record after validation cannot reach the connection
    because the resolver is pinned.
    """
    if not host_to_ips:
        yield
        return
    original = socket.getaddrinfo

    def patched(host: str, *args: Any, **kwargs: Any) -> Any:
        if host in host_to_ips:
            ips = host_to_ips[host]
            port = args[0] if args else kwargs.get("port", 0)
            socktype = kwargs.get("type", socket.SOCK_STREAM)
            results = []
            for ip in ips:
                family = socket.AF_INET6 if ":" in ip else socket.AF_INET
                results.append((family, socktype, 6, "", (ip, port)))
            return results
        return original(host, *args, **kwargs)

    socket.getaddrinfo = patched  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.getaddrinfo = original


def _resolve_public_ips(host: str) -> list[str]:
    """Re-resolve host and return only public IPs. Raises if any is private.

    Sprint 22-2 SEC-21-A-3: DNS rebinding mitigation. Distinct from
    `is_safe_url` (which only returns bool), this returns the IP set
    so we can pin it for the actual connection. Fails closed: any
    private IP in the resolve set causes ValueError.
    """
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError(
            f"DNS resolution failed for {host}: {exc}"
        ) from exc
    public_ips: list[str] = []
    for info in infos:
        ip_str = str(info[4][0])
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _addr_blocked(addr):
            raise ValueError(
                f"DNS rebinding blocked: {host} resolves to private IP {ip_str}"
            )
        public_ips.append(ip_str)
    if not public_ips:
        raise ValueError(f"No public IPs for {host}")
    return public_ips


def safe_http_get_bytes(
    url: str,
    *,
    timeout: float = 25.0,
    max_bytes: int | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    """HTTP GET with DNS pinning and no redirects (stdlib/httpx fetch helper).

    R3-1: Mitigates DNS rebinding between validation and connection for
    ``web_fetch`` and similar tools that must not follow redirects.
    """
    import httpx

    if not is_safe_url(url):
        raise ValueError(f"unsafe url: {url}")
    parsed = urlparse(url.strip())
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no host: {url}")

    pinned_ips = _resolve_public_ips(host)
    hdrs = dict(headers or {})
    with _pinned_dns({host: pinned_ips}):
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            resp = client.get(url, headers=hdrs)
    if resp.status_code in (301, 302, 303, 307, 308):
        raise ValueError("redirect not allowed")
    if resp.status_code >= 400:
        raise httpx.HTTPStatusError(
            f"HTTP {resp.status_code}",
            request=resp.request,
            response=resp,
        )
    body = resp.content
    if max_bytes is not None and len(body) > max_bytes:
        body = body[:max_bytes]
    ctype = str(resp.headers.get("Content-Type") or "")
    return body, ctype


def safe_registry_get(url: str, **kwargs: object) -> object:
    """HTTP GET with no auto-redirects and one validated Location hop.

    Sprint 22-2 SEC-21-A-3: Mitigates DNS rebinding by re-resolving
    after `is_safe_url` passes and pinning the validated IP set for
    the duration of the HTTP call. The pin is host-scoped (other
    lookups fall through to the original resolver) and uses a
    try/finally to restore `socket.getaddrinfo` on success or
    exception.
    """
    import httpx
    from urllib.parse import urljoin

    if not is_safe_url(url):
        raise ValueError(f"unsafe registry url: {url}")
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no host: {url}")

    pinned_ips = _resolve_public_ips(host)
    fetch_kw = httpx_fetch_kwargs()
    fetch_kw.update(kwargs)
    with _pinned_dns({host: pinned_ips}):
        resp = httpx.get(url, **fetch_kw)

    if resp.status_code in (301, 302, 303, 307, 308):
        loc = resp.headers.get("location") or resp.headers.get("Location")
        if loc:
            next_url = urljoin(url, loc)
            if assert_safe_redirect(next_url):
                next_parsed = urlparse(next_url)
                next_host = next_parsed.hostname
                if next_host:
                    next_ips = _resolve_public_ips(next_host)
                    with _pinned_dns({next_host: next_ips}):
                        return httpx.get(next_url, **fetch_kw)
    return resp
