"""Controlled HTTPS download into workspace (opt-in, host allowlist)."""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import ssl
from ipaddress import ip_address
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from butler.tools.path_safety import check_tool_path

logger = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_HOSTS = (
    "github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "pypi.org",
    "files.pythonhosted.org",
)

_BLOCKED_HOST_RE = re.compile(
    r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|::1|\[::1\])$",
    re.I,
)


def download_enabled() -> bool:
    return os.getenv("BUTLER_ENABLE_DOWNLOAD", "").strip() == "1"


def _max_download_bytes() -> int:
    raw = os.getenv("BUTLER_DOWNLOAD_MAX_BYTES", "").strip()
    if not raw:
        return _DEFAULT_MAX_BYTES
    try:
        return max(1024, min(int(raw), 50 * 1024 * 1024))
    except ValueError:
        return _DEFAULT_MAX_BYTES


def _allowed_hosts() -> set[str]:
    raw = os.getenv("BUTLER_DOWNLOAD_ALLOW_HOSTS", "").strip()
    if raw:
        parts = [p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()]
        return set(parts)
    return set(_DEFAULT_HOSTS)


def _host_allowed(hostname: str) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host or _BLOCKED_HOST_RE.match(host):
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    allowed = _allowed_hosts()
    for entry in allowed:
        if host == entry or host.endswith("." + entry):
            return True
    return False


def _resolve_public_ip(hostname: str) -> tuple[bool, str]:
    """Reject private/link-local IPs after DNS resolution (basic SSRF guard)."""
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        return False, f"DNS resolution failed: {exc}"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"Blocked private/reserved address: {addr}"
    return True, ""


def _validate_url(url: str) -> tuple[bool, str]:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        return False, "Only https:// URLs are allowed"
    host = parsed.hostname or ""
    if not _host_allowed(host):
        return False, f"Host not in allowlist: {host}"
    ok, err = _resolve_public_ip(host)
    if not ok:
        return False, err
    return True, ""


def _tool_download_file(
    url: str,
    dest_path: str,
    timeout: int = 60,
    **_,
) -> str:
    if not download_enabled():
        return json.dumps({
            "error": "Download tool is disabled. Set BUTLER_ENABLE_DOWNLOAD=1.",
            "code": "DOWNLOAD_DISABLED",
        })

    ok, err = _validate_url(url)
    if not ok:
        return json.dumps({"error": err, "code": "DOWNLOAD_URL_DENIED"})

    safety = check_tool_path(dest_path, for_write=True)
    if not safety.allowed:
        return json.dumps({"error": safety.error, "code": "DOWNLOAD_PATH_DENIED"})

    try:
        timeout_sec = max(5, min(int(timeout), 120))
    except (TypeError, ValueError):
        return json.dumps({"error": "timeout must be an integer seconds"})

    cap = _max_download_bytes()
    dest = safety.path
    dest.parent.mkdir(parents=True, exist_ok=True)

    req = Request(
        url.strip(),
        headers={"User-Agent": "ButlerDownload/1.0"},
        method="GET",
    )
    try:
        with urlopen(req, timeout=timeout_sec, context=ssl.create_default_context()) as resp:
            cl = resp.headers.get("Content-Length")
            if cl is not None:
                try:
                    if int(cl) > cap:
                        return json.dumps({
                            "error": f"Content-Length {cl} exceeds max {cap}",
                            "code": "DOWNLOAD_TOO_LARGE",
                        })
                except ValueError:
                    pass
            chunks: list[bytes] = []
            total = 0
            while True:
                block = resp.read(65536)
                if not block:
                    break
                total += len(block)
                if total > cap:
                    return json.dumps({
                        "error": f"Download exceeds max {cap} bytes",
                        "code": "DOWNLOAD_TOO_LARGE",
                    })
                chunks.append(block)
            data = b"".join(chunks)
    except URLError as exc:
        return json.dumps({"error": str(exc.reason or exc), "code": "DOWNLOAD_FAILED"})
    except OSError as exc:
        return json.dumps({"error": str(exc), "code": "DOWNLOAD_FAILED"})

    dest.write_bytes(data)
    return json.dumps({
        "success": True,
        "path": str(dest),
        "bytes": len(data),
        "url": url.strip(),
    })


def register_download_tools(register: Callable[..., None]) -> None:
    register(
        name="download_file",
        description=(
            "Download a file over HTTPS into the workspace. "
            "Requires BUTLER_ENABLE_DOWNLOAD=1 and host in BUTLER_DOWNLOAD_ALLOW_HOSTS."
        ),
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "HTTPS URL"},
                "dest_path": {
                    "type": "string",
                    "description": "Destination path relative to workspace",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout seconds (5-120)",
                    "default": 60,
                },
            },
            "required": ["url", "dest_path"],
        },
        handler=_tool_download_file,
        toolset="network",
    )
