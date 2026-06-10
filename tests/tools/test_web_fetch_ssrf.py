"""R3-1: web_fetch DNS rebinding / SSRF TOCTOU hardening."""

from __future__ import annotations

import json
import socket
from unittest import mock

import pytest

from butler.registry import url_safety


def _public_ip_info(ip: str, port: int = 443) -> tuple:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, port))


def _private_ip_info(ip: str, port: int = 443) -> tuple:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, port))


def test_safe_http_get_bytes_re_resolve_blocks_rebinding():
    calls: list[tuple] = []
    plan = [
        [_public_ip_info("1.2.3.4")],
        [_private_ip_info("127.0.0.1")],
    ]

    def stub(host, *args, **kwargs):
        port = args[0] if args else kwargs.get("port", 0)
        calls.append((host, port))
        idx = len(calls) - 1
        return plan[min(idx, len(plan) - 1)]

    with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
        with mock.patch("httpx.Client") as client_cls:
            with pytest.raises(ValueError, match="rebinding|private|No public"):
                url_safety.safe_http_get_bytes("https://evil.example/x")
            assert not client_cls.return_value.__enter__.return_value.get.called


def test_web_fetch_uses_pinned_fetch(monkeypatch):
    monkeypatch.setenv("BUTLER_ENABLE_WEB_FETCH", "1")
    payload = {
        "ok": True,
        "url": "https://example.com",
        "content_type": "text/plain",
        "truncated": False,
        "chars": 5,
        "text": "hello",
    }

    def fake_get(url, **kwargs):
        return (b"hello", "text/plain")

    monkeypatch.setattr(
        "butler.registry.url_safety.safe_http_get_bytes",
        fake_get,
    )
    from butler.tools.web_fetch import tool_web_fetch

    out = json.loads(tool_web_fetch("https://example.com"))
    assert out["ok"] is True
    assert out["text"] == "hello"
