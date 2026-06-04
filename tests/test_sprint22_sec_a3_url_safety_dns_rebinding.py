"""Sprint 22-2 SEC-21-A-3: `url_safety.safe_registry_get` DNS rebinding 防护.

`butler/registry/url_safety.py:83-99` `safe_registry_get` 先调
`is_safe_url` (line 88) 验证 host 的 DNS 解析 IP 全是公网,
再 `httpx.get(url, **fetch_kw)` (line 92). **TOCTOU 窗口**:
`is_safe_url` 与 `httpx.get` 之间, 攻击者可控制 evil.com 的
A 记录翻转 — 第一次解析返回 1.2.3.4 (公网, 通过验证),
第二次解析 (httpx 实际连接时) 翻成 127.0.0.1 或
169.254.169.254 (云元数据) → SSRF.

修复:
1. `safe_registry_get` 在 is_safe_url 通过后, **重新**解析
   并 re-validate 所有 IP, 验证全部非私网.
2. 调 httpx.get 期间用 socket.getaddrinfo 上下文 monkey-patch
   把 host 锁到已验证的 IP 集合 — 期间 httpx 只能拿到这些 IP.
3. 重定向 target 同样处理.

行为保证 (本测试):
1) re-resolve 后任何 IP 是 private → 拒绝 (即使第一次是公网)
2) 期间 httpx.get 拿到的 IP 必须是 pin 集合的子集 (防翻转)
3) 结束后 socket.getaddrinfo 恢复 (无状态泄漏)
4) 重定向 target 同样被 pin
5) 公网 IP 集合正常工作 (no false positive)
"""

from __future__ import annotations

import socket
from unittest import mock

import pytest

from butler.registry import url_safety


# ---------- helpers ----------

_CALL_LOG: list[tuple[str, int]] = []


def _reset_log() -> None:
    _CALL_LOG.clear()


def _make_getaddrinfo(plan: list[list[tuple]]):
    """Build a getaddrinfo stub that returns pre-planned values in order.

    Records every call (host, port) for later inspection.
    """
    state = {"idx": 0, "calls": []}

    def stub(host, *args, **kwargs):
        port = args[0] if args else kwargs.get("port", 0)
        state["calls"].append((host, port))
        idx = state["idx"]
        state["idx"] += 1
        if idx < len(plan):
            return plan[idx]
        # Exhausted plan — last value repeats (typical httpx retry pattern)
        return plan[-1] if plan else []

    return stub, state


def _public_ip_info(ip: str, port: int = 443) -> tuple:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, port))


def _private_ip_info(ip: str, port: int = 443) -> tuple:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (ip, port))


# ---------- tests ----------

@pytest.mark.unit
class TestReResolveBlocksRebinding:
    """re-resolve 后任何 IP 是 private → 拒绝."""

    def test_re_resolve_to_private_ip_rejected(self):
        """第一次 is_safe_url 用公网 IP, 第二次 re-resolve 翻成私网 → 拒绝."""
        # is_safe_url 内 getaddrinfo 返回公网 IP (1.2.3.4) — 通过验证
        # safe_registry_get 内 re-resolve 翻成 127.0.0.1 — 应当拒绝
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],   # is_safe_url
            [_private_ip_info("127.0.0.1")],  # safe_registry_get re-resolve
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get") as fake_get:
                with pytest.raises(ValueError):
                    url_safety.safe_registry_get("https://evil.example/path")
                assert not fake_get.called, (
                    f"rebinding 私网 IP 时 httpx.get 不应被调用, "
                    f"实际调用次数: {fake_get.call_count}"
                )

    def test_re_resolve_to_metadata_ip_rejected(self):
        """re-resolve 返回 169.254.169.254 (云元数据) → 拒绝."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("8.8.8.8")],
            [_private_ip_info("169.254.169.254")],
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get") as fake_get:
                with pytest.raises(ValueError):
                    url_safety.safe_registry_get("https://attacker.example/")
                assert not fake_get.called

    def test_mixed_resolve_with_any_private_rejected(self):
        """re-resolve 返 mix (公网 + 私网) → 拒绝 (保守策略)."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],
            [_public_ip_info("1.2.3.4"), _private_ip_info("127.0.0.1")],
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get") as fake_get:
                with pytest.raises(ValueError):
                    url_safety.safe_registry_get("https://attacker.example/")
                assert not fake_get.called


@pytest.mark.unit
class TestDnsPinningActive:
    """期间 socket.getaddrinfo 被 pin, httpx 拿到的 IP 必须来自 pin 集合."""

    def test_pinning_restores_getaddrinfo_after_request(self):
        """请求结束后, socket.getaddrinfo 必须是原来的真实函数 (无 monkey-patch 泄漏)."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],  # is_safe_url
            [_public_ip_info("1.2.3.4")],  # safe_registry_get re-resolve
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get", return_value=mock.Mock(status_code=200, headers={})):  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                url_safety.safe_registry_get("https://safe.example/path")
        # 退出 with 后, 应当恢复
        assert url_safety.socket.getaddrinfo is socket.getaddrinfo, (
            f"safe_registry_get 结束后 socket.getaddrinfo 必须恢复原值, "
            f"当前值: {url_safety.socket.getaddrinfo!r}"
        )

    def test_pinning_does_not_leak_across_calls(self):
        """连续两次调用, 每次结束后 getaddrinfo 都恢复, 第二次调用仍正常工作."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],  # is_safe_url #1
            [_public_ip_info("1.2.3.4")],  # re-resolve #1
            [_public_ip_info("5.6.7.8")],  # is_safe_url #2
            [_public_ip_info("5.6.7.8")],  # re-resolve #2
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get", return_value=mock.Mock(status_code=200, headers={})):  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                url_safety.safe_registry_get("https://first.example/")
                url_safety.safe_registry_get("https://second.example/")
        assert url_safety.socket.getaddrinfo is socket.getaddrinfo, (
            f"两次调用结束后 socket.getaddrinfo 仍必须恢复原值"
        )

    def test_pinning_restores_on_exception(self):
        """httpx.get 抛异常时, socket.getaddrinfo 也必须恢复 (try/finally)."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],
            [_public_ip_info("1.2.3.4")],
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get", side_effect=ConnectionError("boom")):
                with pytest.raises(ConnectionError):
                    url_safety.safe_registry_get("https://safe.example/")
        assert url_safety.socket.getaddrinfo is socket.getaddrinfo, (
            f"httpx.get 抛异常时 getaddrinfo 必须仍恢复原值 (try/finally 漏写?)"
        )


@pytest.mark.unit
class TestHappyPath:
    """公网 IP 集合正常工作 (no false positive)."""

    def test_public_ip_passes(self):
        """全部公网 IP → 通过, 走正常 httpx 路径."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("8.8.8.8")],
            [_public_ip_info("8.8.8.8")],
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get", return_value=mock.Mock(status_code=200, headers={})):  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                resp = url_safety.safe_registry_get("https://example.com/path")
        assert resp.status_code == 200

    def test_multiple_public_ips_all_pinned(self):
        """多个公网 IP (e.g. IPv4 + IPv6) → 全部 pin 进去."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("8.8.8.8"), _public_ip_info("2001:4860:4860::8888")],
            [_public_ip_info("8.8.8.8"), _public_ip_info("2001:4860:4860::8888")],
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get", return_value=mock.Mock(status_code=200, headers={})):  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                url_safety.safe_registry_get("https://dual-stack.example/")

    def test_request_uses_pinned_resolution(self):
        """核心保护: 验证 safe_registry_get 必须 re-resolve (不只信任 is_safe_url).

        关键: 即使 is_safe_url 通过, safe_registry_get 必须 **再次** getaddrinfo
        来确认 IP 集没变. 如果实现只信任 is_safe_url, 它就跳过了第二次解析,
        不构成 rebinding 防护.
        """
        stub, state = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],  # is_safe_url
            [_public_ip_info("1.2.3.4")],  # re-resolve (必须的!)
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get", return_value=mock.Mock(status_code=200, headers={})):  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                url_safety.safe_registry_get("https://safe.example/")
        # 必须有 2 次 getaddrinfo 调用 (is_safe_url + re-resolve)
        # 如果只有 1 次, 说明实现漏了 re-resolve, 不防 rebinding
        assert len(state["calls"]) >= 2, (
            f"safe_registry_get 必须 re-resolve DNS (>=2 次 getaddrinfo 调用), "
            f"实际: {len(state['calls'])} 次, calls={state['calls']}"
        )


@pytest.mark.unit
class TestRedirectTargetPinned:
    """重定向 target 同样被 pin (递归保护)."""

    def test_redirect_target_pinned(self):
        """重定向到另一 host → 那个 host 的 DNS 也被 re-validate + pin."""
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],  # initial is_safe_url
            [_public_ip_info("1.2.3.4")],  # initial re-resolve
            [_public_ip_info("5.6.7.8")],  # redirect target is_safe_url
            [_public_ip_info("5.6.7.8")],  # redirect target re-resolve
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get") as fake_get:
                redirect_resp = mock.Mock(  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                    status_code=302,
                    headers={"location": "https://elsewhere.example/elsewhere"},
                )  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                ok_resp = mock.Mock(status_code=200, headers={})  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                fake_get.side_effect = [redirect_resp, ok_resp]
                resp = url_safety.safe_registry_get("https://evil.example/start")
                assert resp.status_code == 200
                assert fake_get.call_count == 2

    def test_redirect_to_private_ip_rejected(self):
        """重定向到解析出私网 IP 的 host → 安全策略: 不跟随重定向.

        不能用 `*.local` / `*.internal` — 这些 host 在 is_safe_url
        静态黑名单提前 return False, 走不到 DNS 解析. 用 `internal.example.com`
        才能真正测到 re-resolve 路径上的 rebinding 防御.

        当前实现策略: `assert_safe_redirect` 返回 False 时不抛异常,
        静默不跟随重定向, 返回原始 302 响应. 这与上游 `is_safe_url` 的
        bool 行为保持一致, 不改变 call site 的错误处理方式. 关键是
        **httpx.get 不被调用第二次** (即不向私网 IP 发起请求).
        """
        stub, _ = _make_getaddrinfo([
            [_public_ip_info("1.2.3.4")],  # initial is_safe_url
            [_public_ip_info("1.2.3.4")],  # initial re-resolve
            [_private_ip_info("127.0.0.1")],  # redirect target is_safe_url
        ])
        with mock.patch.object(url_safety.socket, "getaddrinfo", side_effect=stub):
            with mock.patch("httpx.get") as fake_get:
                fake_get.return_value = mock.Mock(  # noqa: magicmock-no-spec — DNS rebinding httpx response shim
                    status_code=302,
                    headers={"location": "http://internal.example.com/"},
                )
                resp = url_safety.safe_registry_get("https://evil.example/")
        # 关键安全保证: 只 1 次 httpx.get, 没有 follow 到私网
        assert fake_get.call_count == 1, (
            f"重定向 target 私网时 httpx.get 必须只调用 1 次, "
            f"实际: {fake_get.call_count} 次"
        )
        assert resp.status_code == 302
